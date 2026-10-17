import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.collectors.geckoterminal import GeckoTerminalCollector
from app.collectors.dexscreener import DexScreenerCollector
from app.config import settings
from app.models.coin import Coin
from app.models.price_history import PriceHistory
from app.models.score import Score

logger = logging.getLogger(__name__)


class DiscoveryService:
    """MODULE 1: Coin Discovery Service.

    Runs collectors, upserts discovered coins, and appends a price_history
    row for every coin seen this cycle (new or existing) so MODULE 6 (trend
    detection) has a time series to work with.
    """

    def __init__(self, db: Session, networks: list[str]):
        self.db = db
        self.gecko = GeckoTerminalCollector(networks=networks)
        self.dexscreener = DexScreenerCollector()

    def run_cycle(self, enrich: bool = True) -> dict:
        discovered = self.gecko.discover()
        new_count = 0
        updated_count = 0
        skipped_count = 0

        for item in discovered:
            if not item.get("contract_address") or not item.get("chain"):
                skipped_count += 1
                continue

            try:
                if enrich and item.get("pair_address"):
                    enrichment = self.dexscreener.enrich_pair(item["chain"], item["pair_address"])
                    if enrichment:
                        # Prefer DexScreener's numbers when present - it's polled
                        # independently, so agreement between sources is itself
                        # a mild trust signal (used later by MODULE 5).
                        for k, v in enrichment.items():
                            if v is not None:
                                item[k] = v

                coin, created = self._upsert_coin(item)
                if created:
                    self._enrich_social_handles(coin)
                self._record_price_history(coin)
                self.db.commit()  # commit per-item so one later failure can't roll back earlier successes

                if created:
                    new_count += 1
                else:
                    updated_count += 1
            except Exception:  # noqa: BLE001 - one bad discovered item shouldn't kill the whole cycle
                self.db.rollback()
                logger.exception(
                    "Discovery failed for item chain=%s contract=%s",
                    item.get("chain"), item.get("contract_address"),
                )
                skipped_count += 1

        result = {
            "discovered": len(discovered),
            "new": new_count,
            "updated": updated_count,
            "skipped": skipped_count,
            "ran_at": datetime.utcnow().isoformat(),
        }
        logger.info("Discovery cycle complete: %s", result)
        return result

    def _upsert_coin(self, item: dict) -> tuple[Coin, bool]:
        coin = (
            self.db.query(Coin)
            .filter(Coin.chain == item["chain"], Coin.contract_address == item["contract_address"])
            .first()
        )

        fields = {
            "pair_address": item.get("pair_address"),
            "source": item.get("source"),
            "symbol": item.get("symbol"),
            "name": item.get("name"),
            "liquidity_usd": item.get("liquidity_usd"),
            "market_cap_usd": item.get("market_cap_usd"),
            "fdv_usd": item.get("fdv_usd"),
            "volume_24h_usd": item.get("volume_24h_usd"),
            "price_usd": item.get("price_usd"),
            "price_change_1h": item.get("price_change_1h"),
            "price_change_24h": item.get("price_change_24h"),
        }

        if coin is None:
            coin = Coin(
                chain=item["chain"],
                contract_address=item["contract_address"],
                launch_time=item.get("launch_time"),
                **fields,
            )
            self.db.add(coin)
            self.db.flush()  # get coin.id without a full commit
            return coin, True

        for k, v in fields.items():
            setattr(coin, k, v)
        self.db.flush()
        return coin, False

    def _enrich_social_handles(self, coin: Coin) -> None:
        """Fetch telegram_handle/twitter_handle. Best-effort: failures are
        silent since this is enrichment, not core discovery data. Always
        records social_enrichment_checked_at (hit or miss) so
        re_enrich_missing_social_handles() knows when this coin was last
        tried and can space out retries rather than hammering GeckoTerminal
        every cycle for coins that still have nothing."""
        coin.social_enrichment_checked_at = datetime.utcnow()
        try:
            info = self.gecko.get_token_info(coin.chain, coin.contract_address)
        except Exception:  # noqa: BLE001
            logger.warning("Social handle enrichment failed for coin id=%s", coin.id)
            return
        if not info:
            return
        coin.telegram_handle = info.get("telegram_handle")
        coin.twitter_handle = info.get("twitter_handle")

    def re_enrich_missing_social_handles(
        self, max_coins: int = 150, recheck_after_hours: int = 24, give_up_after_days: int = 14
    ) -> dict:
        """Periodically re-check coins that had NO telegram_handle at
        discovery time. This closes a real coverage gap: many projects add
        their Telegram link to GeckoTerminal a few hours or days AFTER
        initial launch, not at the exact moment we first discover them -
        the original one-time-only enrichment in run_cycle() would never
        catch that. Bounded three ways so this can't run away: a per-cycle
        coin cap, a minimum gap between re-checks of the same coin, and a
        hard cutoff (give_up_after_days) after which a coin that still has
        nothing is assumed unlikely to ever set one, so we stop spending
        GeckoTerminal calls on it."""
        cutoff_recheck = datetime.utcnow() - timedelta(hours=recheck_after_hours)
        cutoff_give_up = datetime.utcnow() - timedelta(days=give_up_after_days)

        candidates = (
            self.db.query(Coin)
            .filter(
                Coin.is_active.is_(True),
                Coin.telegram_handle.is_(None),
                Coin.first_seen_at >= cutoff_give_up,
                (Coin.social_enrichment_checked_at.is_(None)) | (Coin.social_enrichment_checked_at < cutoff_recheck),
            )
            .order_by(Coin.first_seen_at.desc())  # prioritize newer coins - most likely to still gain a handle
            .limit(max_coins)
            .all()
        )

        rechecked = 0
        newly_found = 0
        for coin in candidates:
            coin_id_for_logging = coin.id
            try:
                had_handle_before = bool(coin.telegram_handle)
                self._enrich_social_handles(coin)
                self.db.commit()
                rechecked += 1
                if not had_handle_before and coin.telegram_handle:
                    newly_found += 1
            except Exception:  # noqa: BLE001
                self.db.rollback()
                logger.exception("Re-enrichment failed for coin id=%s", coin_id_for_logging)

        return {"rechecked": rechecked, "newly_found_handle": newly_found, "candidates_available": len(candidates)}

    def refresh_existing_prices(self, batch_size: int = 30, recheck_after_hours: int | None = None) -> dict:
        """Refresh CURRENT price/liquidity/volume for already-known active
        coins, batched up to 30 per GeckoTerminal API call (their
        pools/multi/{addresses} limit). This is the fix for a real,
        significant gap found via production data: run_cycle() above only
        ever sees a coin ONCE, whenever it happens to appear in the
        new_pools feed - once a coin ages out of that "newest" window
        (which happens within its first hour or so), nothing in this
        system ever checks its price again. price_history freezes there
        permanently, and MODULE 6 (trend detection) can never mature past
        whatever was captured in that brief initial window - confirmed via
        real coins 20+ hours old still showing zero trend signal. This
        method is what actually closes that gap: it doesn't care whether a
        coin is "new," only whether it's still active and has a known
        pair_address to check.

        BOUNDED, same pattern as risk_service/wallet_service: only coins
        that are new or haven't been refreshed in recheck_after_hours are
        included. Real pacing math (see collectors/geckoterminal.py's
        address-count-proportional wait, added after observing persistent
        429s) means a full pass across ~1700 coins takes roughly an hour -
        without bounding, this would hit the exact same
        "cycle takes longer than its own interval" overlap problem already
        diagnosed and fixed for risk/wallet checks tonight."""
        refreshed = 0
        batch_api_failures = 0
        no_match_failures = 0
        recheck_hours = recheck_after_hours if recheck_after_hours is not None else settings.price_refresh_recheck_hours
        recheck_cutoff = datetime.utcnow() - timedelta(hours=recheck_hours)
        for network in self.gecko.networks:
            coins = (
                self.db.query(Coin)
                .outerjoin(Score, Score.coin_id == Coin.id)
                .filter(
                    Coin.is_active.is_(True),
                    Coin.chain == network,
                    Coin.pair_address.isnot(None),
                    (Score.id.is_(None))
                    | (Score.price_refreshed_at.is_(None))
                    | (Score.price_refreshed_at < recheck_cutoff),
                )
                .all()
            )
            for i in range(0, len(coins), batch_size):
                batch = coins[i : i + batch_size]
                pair_addresses = [c.pair_address for c in batch]
                try:
                    fresh_data = self.gecko.refresh_prices(network, pair_addresses)
                except Exception:  # noqa: BLE001 - one bad batch shouldn't kill the whole refresh
                    logger.exception("Price refresh batch failed for network=%s", network)
                    batch_api_failures += len(batch)
                    continue

                # Case-insensitive matching: EVM addresses (eth/base) are
                # functionally case-insensitive, and different GeckoTerminal
                # endpoints (new_pools vs pools/multi) aren't guaranteed to
                # return the exact same casing for the same pool. A naive
                # exact-string match would silently miss real matches here.
                by_pair_address = {
                    d["pair_address"].lower(): d for d in fresh_data if d.get("pair_address")
                }
                unmatched_this_batch = []
                for coin in batch:
                    item = by_pair_address.get(coin.pair_address.lower())
                    if not item:
                        no_match_failures += 1
                        unmatched_this_batch.append(f"{coin.symbol or '?'}:{coin.pair_address}")
                        continue
                    try:
                        self._apply_price_update(coin, item)
                        self.db.commit()  # commit per-coin so one later failure can't roll back earlier successes
                        refreshed += 1
                    except Exception:  # noqa: BLE001
                        self.db.rollback()
                        logger.exception("Failed applying price refresh for coin id=%s", coin.id)
                        no_match_failures += 1

                if unmatched_this_batch:
                    # Logged as a batch summary, not one line per coin, to
                    # avoid flooding the logs when many pools genuinely no
                    # longer exist (common for dead/rugged meme coins) -
                    # but still gives enough to diagnose a systematic issue
                    # (e.g. every failure being on one specific chain would
                    # point at something other than "pool doesn't exist").
                    logger.info(
                        "Price refresh: %d/%d coins in this %s batch had no matching pool returned: %s",
                        len(unmatched_this_batch), len(batch), network, ", ".join(unmatched_this_batch[:10]),
                    )

        return {
            "refreshed": refreshed,
            "no_match_failures": no_match_failures,
            "batch_api_failures": batch_api_failures,
            "ran_at": datetime.utcnow().isoformat(),
        }

    def _apply_price_update(self, coin: Coin, item: dict) -> None:
        for field in (
            "liquidity_usd", "market_cap_usd", "fdv_usd", "volume_24h_usd",
            "price_usd", "price_change_1h", "price_change_24h",
        ):
            if item.get(field) is not None:
                setattr(coin, field, item[field])
        self.db.flush()

        score = self.db.query(Score).filter(Score.coin_id == coin.id).first()
        if score is None:
            score = Score(coin_id=coin.id)
            self.db.add(score)
        score.price_refreshed_at = datetime.utcnow()

        self._record_price_history(coin)

    def _record_price_history(self, coin: Coin) -> None:
        snapshot = PriceHistory(
            coin_id=coin.id,
            price_usd=coin.price_usd,
            liquidity_usd=coin.liquidity_usd,
            market_cap_usd=coin.market_cap_usd,
            volume_24h_usd=coin.volume_24h_usd,
        )
        self.db.add(snapshot)
