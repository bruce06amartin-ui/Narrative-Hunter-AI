import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.channels.discord import DiscordChannel
from app.channels.telegram import TelegramChannel
from app.channels.email import EmailChannel
from app.config import settings
from app.services.liquidity_sanity import is_liquidity_plausible, is_actively_trading
from app.models.alert import Alert
from app.models.coin import Coin
from app.models.price_history import PriceHistory
from app.models.score import HistoricalScore
from app.models.wallet_transaction import WalletTransaction
from app.services.wallet_service import WalletIntelligenceService

logger = logging.getLogger(__name__)


class AlertService:
    """MODULE 9: Alerts.

    Spec conditions and their status:
      - "Overall Score > configurable threshold"  -> IMPLEMENTED (fires once
        per upward crossing, using consecutive HistoricalScore rows so it
        doesn't spam every cycle while the score stays elevated).
      - "Risk score changes"                       -> IMPLEMENTED (fires when
        risk_score moves >= ALERT_RISK_SCORE_CHANGE_THRESHOLD points between
        two consecutive scoring cycles, either direction).
      - "Multiple smart wallets buy"                -> IMPLEMENTED (EVM chains
        only, via MODULE 3/WalletIntelligenceService - fires when at least
        WALLET_ACCUMULATION_MIN_STRONG_WALLETS currently-holding wallets
        with reputation_score >= WALLET_STRONG_REPUTATION_THRESHOLD entered
        within the lookback window; time-cooldown dedup rather than
        crossing-based, since this is a sustained-state condition).
      - "Narrative increases rapidly"               -> IMPLEMENTED (via
        MODULE 2/7/NarrativeScannerService - fires once when narrative_score
        crosses from below to at/above ALERT_NARRATIVE_SCORE_THRESHOLD,
        same crossing-based dedup as the overall-score condition. Requires
        at least one narrative source configured AND ANTHROPIC_API_KEY set;
        otherwise narrative_score stays null and this never fires).
      - "Large whale enters"                        -> IMPLEMENTED (EVM chains
        only, via MODULE 3 wallet_transactions - estimates USD value as
        transaction amount × the nearest recorded price_history snapshot
        (same proxy approach as wallet ROI in MODULE 3, not an exact
        block-time price). Fires on the single largest qualifying buy in
        the lookback window, deduped so an already-flagged whale doesn't
        re-fire every alert cycle unless a strictly larger one shows up).

    Not in the original spec's alert list, but added for consistency once
    MODULE 4 existed: community_score_threshold, same crossing-based
    pattern as overall/narrative. A fast-growing, highly-engaged community
    is exactly the kind of thing you'd want a heads-up on.

    Delivery: Discord (webhook), Telegram (bot), Email (SMTP) - each is
    independently optional based on whether its config is set (see
    config.py). If zero channels are configured, alerts are still recorded
    in the `alerts` table (visible via the API/dashboard) with
    delivered=False, so nothing is silently lost even with no channels wired up.
    """

    def __init__(self, db: Session):
        self.db = db
        self.channels = [DiscordChannel(), TelegramChannel(), EmailChannel()]
        self.wallet_service = WalletIntelligenceService(db)

    def check_all_active(self) -> dict:
        coins = self.db.query(Coin).filter(Coin.is_active.is_(True)).all()
        triggered = 0
        for coin in coins:
            coin_id_for_logging = coin.id
            try:
                triggered += len(self.check_coin(coin))
                self.db.commit()  # commit per-coin so one later failure can't roll back earlier successes
            except Exception:  # noqa: BLE001 - one bad coin shouldn't kill the run
                self.db.rollback()
                logger.exception("Alert check failed for coin id=%s", coin_id_for_logging)
        active_channels = [c.name for c in self.channels if c.is_configured()]
        return {
            "alerts_triggered": triggered,
            "total_active_coins": len(coins),
            "channels_configured": active_channels,
            "ran_at": datetime.utcnow().isoformat(),
        }

    def check_coin(self, coin: Coin) -> list[Alert]:
        new_alerts: list[Alert] = []

        recent = (
            self.db.query(HistoricalScore)
            .filter(HistoricalScore.coin_id == coin.id)
            .order_by(HistoricalScore.recorded_at.desc())
            .limit(2)
            .all()
        )
        if len(recent) >= 2:
            current, previous = recent[0], recent[1]

            overall_alert = self._check_overall_score_threshold(coin, current, previous)
            if overall_alert:
                new_alerts.append(overall_alert)

            risk_alert = self._check_risk_score_change(coin, current, previous)
            if risk_alert:
                new_alerts.append(risk_alert)

            narrative_alert = self._check_narrative_score_threshold(coin, current, previous)
            if narrative_alert:
                new_alerts.append(narrative_alert)

            community_alert = self._check_community_score_threshold(coin, current, previous)
            if community_alert:
                new_alerts.append(community_alert)

        wallet_alert = self._check_smart_wallet_accumulation(coin)
        if wallet_alert:
            new_alerts.append(wallet_alert)

        whale_alert = self._check_whale_entry(coin)
        if whale_alert:
            new_alerts.append(whale_alert)

        for alert in new_alerts:
            self.db.add(alert)
            self.db.flush()  # get alert.id before dispatch
            self._dispatch(alert, coin)

        return new_alerts

    def _passes_liquidity_gate(self, coin: Coin) -> bool:
        """Combines three checks: the minimum-liquidity threshold, the
        manipulation sanity check (fake/manipulated liquidity claims),
        and now also a dead-trading check (real production case: a user
        reported bot-alerted coins whose actual last transaction was
        3-11+ hours old, well past any real activity - genuinely stopped
        trading, distinct from the manipulation case since either a real
        or a fake liquidity figure can accompany a coin nobody is
        actually trading anymore)."""
        liquidity = coin.liquidity_usd or 0
        if liquidity < settings.alert_min_liquidity_usd:
            return False
        if not is_liquidity_plausible(coin.liquidity_usd, coin.volume_24h_usd):
            return False
        return is_actively_trading(coin.volume_24h_usd)

    def _check_overall_score_threshold(
        self, coin: Coin, current: HistoricalScore, previous: HistoricalScore
    ) -> Alert | None:
        threshold = settings.alert_overall_score_threshold
        crossed_up = (
            current.overall_score >= threshold
            and (previous.overall_score is None or previous.overall_score < threshold)
        )
        if not crossed_up:
            return None

        # Risk gate - same principle already proven correct for paper
        # trading: overall_score's risk penalty is proportional, not a hard
        # cutoff, so a coin with a genuinely concerning risk_score can still
        # cross the alert threshold if its other signals are strong enough.
        # Real user data showed this happening: ~27% of a batch of alerts
        # turned out to be already-rugged coins - this gate is the fix.
        # risk_score being null (not yet checked) does NOT block the alert,
        # same as the paper trading gate - only a genuinely high, CONFIRMED
        # risk_score does.
        if current.risk_score is not None and current.risk_score >= settings.alert_risk_gate_max:
            logger.info(
                "Overall score alert skipped for coin id=%s: crossed %.0f but risk_score=%.0f (gate is %.0f)",
                coin.id, threshold, current.risk_score, settings.alert_risk_gate_max,
            )
            return None

        # Minimum liquidity gate - real user feedback: alerts were firing
        # for coins so small they weren't meaningful opportunities, purely
        # because they crossed the score threshold on other signals. Unlike
        # risk_score, liquidity is essentially always known by the time a
        # coin has a score at all (it's a core discovery field), so a
        # missing value is treated the same as zero here rather than given
        # a benefit-of-the-doubt pass.
        if not self._passes_liquidity_gate(coin):
            logger.info(
                "Overall score alert skipped for coin id=%s: crossed %.0f but liquidity_usd=%s (gate is %.0f)",
                coin.id, threshold, coin.liquidity_usd, settings.alert_min_liquidity_usd,
            )
            return None

        if self._already_alerted(coin.id, "overall_score_threshold", current.recorded_at):
            return None

        return Alert(
            coin_id=coin.id,
            alert_type="overall_score_threshold",
            severity="info",
            message=(
                f"Overall score crossed above {threshold:.0f} "
                f"(now {current.overall_score:.0f}, was {previous.overall_score or 0:.0f})."
            ),
            trigger_value=current.overall_score,
            previous_value=previous.overall_score,
        )

    def _check_risk_score_change(
        self, coin: Coin, current: HistoricalScore, previous: HistoricalScore
    ) -> Alert | None:
        if current.risk_score is None or previous.risk_score is None:
            return None

        delta = current.risk_score - previous.risk_score
        if abs(delta) < settings.alert_risk_score_change_threshold:
            return None
        # Positive-only filter: risk INCREASING is the one genuinely
        # negative-news alert type in this whole system (every other alert
        # type - score thresholds, whale entries, smart wallet
        # accumulation - is inherently a positive signal by construction).
        # A risk DECREASE (e.g. liquidity just got locked) still counts as
        # positive news and is allowed through even in this mode.
        if settings.alert_positive_only and delta > 0:
            return None
        # Same liquidity gate as the other three alert types - this was the
        # actual gap: risk_score_change never had it, and real user data
        # showed it firing repeatedly for negligible-liquidity coins (20
        # consecutive risk alerts, all on one chain, many likely tiny).
        if not self._passes_liquidity_gate(coin):
            return None
        if self._already_alerted(coin.id, "risk_score_change", current.recorded_at):
            return None

        direction = "increased" if delta > 0 else "decreased"
        severity = "critical" if delta > 0 and current.risk_score >= 70 else "warning"

        return Alert(
            coin_id=coin.id,
            alert_type="risk_score_change",
            severity=severity,
            message=(
                f"Risk score {direction} by {abs(delta):.0f} points "
                f"(now {current.risk_score:.0f}, was {previous.risk_score:.0f})."
            ),
            trigger_value=current.risk_score,
            previous_value=previous.risk_score,
        )

    def _check_narrative_score_threshold(
        self, coin: Coin, current: HistoricalScore, previous: HistoricalScore
    ) -> Alert | None:
        if current.narrative_score is None:
            return None
        threshold = settings.alert_narrative_score_threshold
        crossed_up = current.narrative_score >= threshold and (
            previous.narrative_score is None or previous.narrative_score < threshold
        )
        if not crossed_up:
            return None
        if current.risk_score is not None and current.risk_score >= settings.alert_risk_gate_max:
            return None
        if not self._passes_liquidity_gate(coin):
            return None
        if self._already_alerted(coin.id, "narrative_score_threshold", current.recorded_at):
            return None

        return Alert(
            coin_id=coin.id,
            alert_type="narrative_score_threshold",
            severity="info",
            message=(
                f"Narrative score crossed above {threshold:.0f} "
                f"(now {current.narrative_score:.0f}, was {previous.narrative_score or 0:.0f}) - "
                "the narrative is picking up rapidly."
            ),
            trigger_value=current.narrative_score,
            previous_value=previous.narrative_score,
        )

    def _check_community_score_threshold(
        self, coin: Coin, current: HistoricalScore, previous: HistoricalScore
    ) -> Alert | None:
        if current.community_score is None:
            return None
        threshold = settings.alert_community_score_threshold
        crossed_up = current.community_score >= threshold and (
            previous.community_score is None or previous.community_score < threshold
        )
        if not crossed_up:
            return None
        if current.risk_score is not None and current.risk_score >= settings.alert_risk_gate_max:
            return None
        if not self._passes_liquidity_gate(coin):
            return None
        if self._already_alerted(coin.id, "community_score_threshold", current.recorded_at):
            return None

        return Alert(
            coin_id=coin.id,
            alert_type="community_score_threshold",
            severity="info",
            message=(
                f"Community score crossed above {threshold:.0f} "
                f"(now {current.community_score:.0f}, was {previous.community_score or 0:.0f})."
            ),
            trigger_value=current.community_score,
            previous_value=previous.community_score,
        )

    def _check_whale_entry(self, coin: Coin) -> Alert | None:
        if coin.chain.lower() not in ("eth", "ethereum", "base"):
            return None  # MODULE 3 wallet data only covers EVM chains

        cutoff = datetime.utcnow() - timedelta(hours=settings.whale_entry_lookback_hours)
        rows = (
            self.db.query(WalletTransaction)
            .filter(
                WalletTransaction.coin_id == coin.id,
                WalletTransaction.direction == "in",
                WalletTransaction.block_timestamp >= cutoff,
            )
            .order_by(WalletTransaction.amount.desc())
            .limit(20)
            .all()
        )
        if not rows:
            return None

        best_usd_value = None
        best_tx = None
        for tx in rows:
            price = self._nearest_price_usd(coin.id, tx.block_timestamp)
            if price is None:
                continue
            usd_value = tx.amount * price
            # Plausibility sanity check, found via real production data: a
            # coin with only $67k liquidity showed a "whale" alert
            # claiming a single $228k purchase - over 3x the entire
            # pool's liquidity, which is essentially impossible in a real
            # AMM (bonding-curve math means a single trade asymptotically
            # approaches but never reaches 100% of a pool's liquidity).
            # This isn't necessarily a parsing bug on our side - decimals
            # ARE read correctly per-token from Etherscan (see
            # collectors/etherscan.py) - it's more likely either bad
            # upstream data or a token contract deliberately misreporting
            # its own decimals() to inflate apparent transaction sizes, a
            # known scam-token evasion pattern. Either way, the resulting
            # dollar estimate isn't trustworthy enough to alert on, same
            # "don't trust the number just because it was computed"
            # philosophy as the liquidity manipulation check.
            if coin.liquidity_usd and usd_value >= coin.liquidity_usd:
                logger.info(
                    "Skipping implausible whale_entry candidate for coin id=%s: "
                    "$%.2f estimate exceeds coin's own $%.2f liquidity",
                    coin.id, usd_value, coin.liquidity_usd,
                )
                continue
            if best_usd_value is None or usd_value > best_usd_value:
                best_usd_value = usd_value
                best_tx = tx

        if best_usd_value is None or best_usd_value < settings.whale_entry_usd_threshold:
            return None
        if not self._passes_liquidity_gate(coin):
            return None

        # Dedup: skip if we've already flagged a whale of this size or
        # larger for this coin within the cooldown window - a strictly
        # bigger whale than any previously flagged one still gets its own alert.
        cooldown_cutoff = datetime.utcnow() - timedelta(hours=settings.whale_entry_alert_cooldown_hours)
        existing = (
            self.db.query(Alert)
            .filter(
                Alert.coin_id == coin.id,
                Alert.alert_type == "whale_entry",
                Alert.created_at >= cooldown_cutoff,
                Alert.trigger_value >= best_usd_value,
            )
            .first()
        )
        if existing:
            return None

        return Alert(
            coin_id=coin.id,
            alert_type="whale_entry",
            severity="info",
            message=(
                f"A wallet bought an estimated ${best_usd_value:,.0f} of this coin "
                f"in the last {settings.whale_entry_lookback_hours}h "
                "(estimate: transfer amount × nearest recorded price, not exact block-time price)."
            ),
            trigger_value=best_usd_value,
            previous_value=None,
        )

    def _nearest_price_usd(self, coin_id, ts: datetime) -> float | None:
        before = (
            self.db.query(PriceHistory)
            .filter(PriceHistory.coin_id == coin_id, PriceHistory.recorded_at <= ts)
            .order_by(PriceHistory.recorded_at.desc())
            .first()
        )
        if before and before.price_usd:
            return before.price_usd
        after = (
            self.db.query(PriceHistory)
            .filter(PriceHistory.coin_id == coin_id, PriceHistory.recorded_at >= ts)
            .order_by(PriceHistory.recorded_at.asc())
            .first()
        )
        return after.price_usd if after else None

    def _check_smart_wallet_accumulation(self, coin: Coin) -> Alert | None:
        if coin.chain.lower() not in ("eth", "ethereum", "base"):
            return None  # MODULE 3 wallet data only covers EVM chains - see wallet_service.py

        strong_count = self.wallet_service.count_strong_holding_wallets(coin.id)
        if strong_count < settings.wallet_accumulation_min_strong_wallets:
            return None
        if not self._passes_liquidity_gate(coin):
            return None
        if self._recently_alerted(
            coin.id, "smart_wallet_accumulation", settings.wallet_accumulation_alert_cooldown_hours
        ):
            return None

        return Alert(
            coin_id=coin.id,
            alert_type="smart_wallet_accumulation",
            severity="info",
            message=(
                f"{strong_count} wallets with a strong track record on this platform "
                f"(reputation ≥ {settings.wallet_strong_reputation_threshold:.0f}) have accumulated "
                f"a position within the last {settings.wallet_accumulation_lookback_hours}h."
            ),
            trigger_value=float(strong_count),
            previous_value=None,
        )

    def _already_alerted(self, coin_id, alert_type: str, since: datetime) -> bool:
        """Dedup guard: the alert-check cycle can run more often than the
        scoring cycle (independent intervals), which would otherwise re-fire
        the same alert on every check as long as the same two HistoricalScore
        rows are still the latest. An alert of this type created at/after the
        current data point's timestamp means this exact crossing/change was
        already handled."""
        existing = (
            self.db.query(Alert)
            .filter(Alert.coin_id == coin_id, Alert.alert_type == alert_type, Alert.created_at >= since)
            .first()
        )
        return existing is not None

    def _recently_alerted(self, coin_id, alert_type: str, cooldown_hours: float) -> bool:
        """Time-based dedup for sustained-state conditions (unlike the
        crossing-based checks above, "3+ strong wallets holding" doesn't
        have a natural before/after pair to diff against - it can stay
        true for days, so a cooldown window is used instead of a one-time
        crossing check."""
        cutoff = datetime.utcnow() - timedelta(hours=cooldown_hours)
        existing = (
            self.db.query(Alert)
            .filter(Alert.coin_id == coin_id, Alert.alert_type == alert_type, Alert.created_at >= cutoff)
            .first()
        )
        return existing is not None

    def _dispatch(self, alert: Alert, coin: Coin) -> None:
        coin_label = f"{coin.symbol or coin.contract_address[:8]} ({coin.chain})"
        trade_url = self._build_trade_url(coin)
        delivered_channels = []
        errors = []

        for channel in self.channels:
            if not channel.is_configured():
                continue
            try:
                if channel.send(alert, coin_label, trade_url):
                    delivered_channels.append(channel.name)
            except Exception as e:  # noqa: BLE001 - one channel's crash shouldn't block others
                logger.exception("Channel %s raised while sending alert %s", channel.name, alert.id)
                errors.append(f"{channel.name}: {e}")

        alert.channels_delivered = ",".join(delivered_channels) if delivered_channels else None
        alert.delivered = len(delivered_channels) > 0
        alert.delivery_error = "; ".join(errors) if errors else None
        self.db.flush()

    def _build_trade_url(self, coin: Coin) -> str | None:
        """Direct link to the coin's GeckoTerminal pool page - the SAME
        platform pair_address originated from, not a different one we're
        hoping has separately indexed the same pool.

        This replaced an earlier DexScreener-based version after real user
        reports: 2 of 3 alert links pointed to pools DexScreener had never
        indexed, despite GeckoTerminal (our actual data source) having had
        them the whole time. DexScreener and GeckoTerminal are separate
        aggregators with separate coverage - there was never a guarantee
        they'd overlap for a given pool, especially new/low-volume ones.
        Linking back to the coin's own source data eliminates that
        cross-platform assumption entirely rather than trying to verify it.

        Network slugs verified directly against real, currently-indexed
        GeckoTerminal pages (not just documentation mentions) for all three
        chains this project tracks: geckoterminal.com/solana/pools/...,
        .../eth/pools/..., .../base/pools/... - all confirmed to use the
        EXACT same slug this project already stores in Coin.chain, so no
        translation map is needed (unlike the earlier DexScreener version,
        which needed one)."""
        if not coin.pair_address:
            return None
        return f"https://www.geckoterminal.com/{coin.chain.lower()}/pools/{coin.pair_address}"

    def cleanup_old_alerts(self, retention_days: int | None = None) -> dict:
        """Deletes alerts older than the retention window - a genuine
        delete, not a soft-hide, per explicit request. The default
        (ALERT_RETENTION_DAYS, 30 days) is deliberately generous: real
        alert history has repeatedly had genuine diagnostic value this
        session (e.g. comparing an alert's created_at against when a fix
        was deployed, to tell "stale, pre-fix data" apart from "a new,
        real problem"). A short retention window would have destroyed
        exactly the evidence that made several of tonight's fixes
        possible to confirm. 30 days balances that against not letting
        the table grow unbounded forever."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days or settings.alert_retention_days)
        deleted_count = (
            self.db.query(Alert)
            .filter(Alert.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return {
            "deleted": deleted_count,
            "retention_days": retention_days or settings.alert_retention_days,
            "ran_at": datetime.utcnow().isoformat(),
        }
