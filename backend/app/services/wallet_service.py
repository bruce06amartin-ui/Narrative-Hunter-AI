"""
MODULE 3: Wallet Intelligence.

Scope and honest limitations (read before trusting these numbers):

CHAIN COVERAGE: EVM only (eth, base) via Etherscan's unified V2 API. Solana
is NOT covered - pump.fun/Raydium wallet activity would need a dedicated
Solana indexer (e.g. Helius's Enhanced Transactions API, which requires
DEX-specific instruction parsing) that couldn't be verified without live
network access in this build environment. Given Solana is likely the
primary chain for meme coin activity, this is a real gap, not a minor one -
wallet_score/reputation simply won't exist for Solana coins.

WHAT "BUY"/"SELL" MEANS HERE: an ERC20 transfer where a wallet is the
recipient is treated as a proxy "buy" (direction='in'); where it's the
sender, a proxy "sell" (direction='out'). This can't distinguish a real DEX
trade from a wallet-to-wallet transfer (e.g. moving to a different wallet
you own) - there's no router/DEX address registry here to disambiguate.
The coin's own known pair_address is excluded so the AMM pool itself isn't
scored as a "wallet," but other pool/router addresses aren't filtered.

WHAT "ROI" MEANS HERE: there's no per-block historical USD price oracle in
this codebase. Entry price is approximated as the nearest PriceHistory
snapshot we happened to record (discovery/scoring cycles run every few
minutes) to the wallet's first 'in' transaction - not the actual price at
that exact block. ROI is (current price - that snapshot) / that snapshot.
Treat this as directionally useful, not precise.

WHAT "REPUTATION" MEANS HERE: computed only from coins THIS platform has
discovered and this wallet has transacted on - not the wallet's real
lifetime trading history (which isn't observable from token-contract
transfer events alone).
"""

import logging
import statistics
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.chains import EVM_WALLET_SUPPORTED_CHAINS
from app.collectors.etherscan import EtherscanCollector
from app.config import settings
from app.models.coin import Coin
from app.models.price_history import PriceHistory
from app.models.score import Score
from app.models.wallet import Wallet
from app.models.wallet_transaction import WalletTransaction

logger = logging.getLogger(__name__)

BURN_ADDRESSES = {
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
}
HOLDING_EPSILON = 1e-9


class WalletIntelligenceService:
    def __init__(self, db: Session):
        self.db = db
        self.collector = EtherscanCollector()

    def check_all_active(self) -> dict:
        if not self.collector.is_configured():
            return {
                "skipped": True,
                "reason": "ETHERSCAN_API_KEY not configured",
                "ran_at": datetime.utcnow().isoformat(),
            }

        total_evm_active = (
            self.db.query(Coin)
            .filter(Coin.is_active.is_(True), Coin.chain.in_(EVM_WALLET_SUPPORTED_CHAINS))
            .count()
        )

        recheck_cutoff = datetime.utcnow() - timedelta(hours=settings.wallet_recheck_hours)
        coins = (
            self.db.query(Coin)
            .outerjoin(Score, Score.coin_id == Coin.id)
            .filter(
                Coin.is_active.is_(True),
                Coin.chain.in_(EVM_WALLET_SUPPORTED_CHAINS),
                (Score.id.is_(None))
                | (Score.wallet_checked_at.is_(None))
                | (Score.wallet_checked_at < recheck_cutoff),
            )
            .all()
        )
        ingested = 0
        wallets_updated = 0
        for coin in coins:
            coin_id_for_logging = coin.id  # capture before any risk of a broken session
            try:
                result = self.ingest_coin(coin)
                self.db.commit()  # commit per-coin so one later failure can't roll back earlier successes
                ingested += 1
                wallets_updated += result["wallets_touched"]
            except Exception:  # noqa: BLE001 - one bad coin shouldn't kill the run
                # Roll back so this coin's partial/failed work doesn't leave
                # the session in a broken state for every coin after it -
                # without this, one bad coin poisons the entire remaining
                # batch with PendingRollbackError, not just itself.
                self.db.rollback()
                logger.exception("Wallet ingest failed for coin id=%s", coin_id_for_logging)
        return {
            "coins_processed": ingested,
            "wallets_touched": wallets_updated,
            "due_for_check_this_cycle": len(coins),
            "total_evm_active": total_evm_active,
            "ran_at": datetime.utcnow().isoformat(),
        }

    def ingest_coin(self, coin: Coin) -> dict:
        transfers = self.collector.get_token_transfers(coin.chain, coin.contract_address)
        pair_lower = (coin.pair_address or "").lower()
        touched_wallet_ids: set = set()
        # Etherscan can return the exact same (tx_hash, address, direction)
        # more than once within a single response - e.g. a multi-hop swap
        # can log the same wallet's transfer twice. The DB-based existence
        # check in _record_transaction only sees rows already flushed to
        # Postgres, so a duplicate seen twice *within this same batch*
        # (before any flush) slips past it and both attempts hit the unique
        # constraint at flush time. Track what's been queued this cycle too.
        seen_this_cycle: set[tuple[str, str, str]] = set()

        for t in transfers:
            for address, direction in ((t["to_address"], "in"), (t["from_address"], "out")):
                if address == pair_lower or address in BURN_ADDRESSES:
                    continue
                wallet = self._get_or_create_wallet(coin.chain, address)
                dedup_key = (t["tx_hash"], str(wallet.id), direction)
                if dedup_key in seen_this_cycle:
                    continue
                seen_this_cycle.add(dedup_key)
                if self._record_transaction(wallet, coin, t, direction):
                    touched_wallet_ids.add(wallet.id)

        self.db.flush()

        for wallet_id in touched_wallet_ids:
            wallet = self.db.query(Wallet).filter(Wallet.id == wallet_id).first()
            if wallet:
                self._recompute_wallet_reputation(wallet)

        self._update_coin_wallet_score(coin)
        self.db.flush()
        return {"transfers_seen": len(transfers), "wallets_touched": len(touched_wallet_ids)}

    def _get_or_create_wallet(self, chain: str, address: str) -> Wallet:
        wallet = self.db.query(Wallet).filter(Wallet.chain == chain, Wallet.address == address).first()
        if wallet is None:
            wallet = Wallet(chain=chain, address=address)
            self.db.add(wallet)
            self.db.flush()
        return wallet

    def _record_transaction(self, wallet: Wallet, coin: Coin, transfer: dict, direction: str) -> bool:
        """Insert a WalletTransaction if not already ingested. Returns True
        if a new row was created (used to decide whether this wallet needs
        recomputing this cycle)."""
        existing = (
            self.db.query(WalletTransaction)
            .filter(
                WalletTransaction.tx_hash == transfer["tx_hash"],
                WalletTransaction.wallet_id == wallet.id,
                WalletTransaction.direction == direction,
            )
            .first()
        )
        if existing:
            return False

        self.db.add(
            WalletTransaction(
                wallet_id=wallet.id,
                coin_id=coin.id,
                tx_hash=transfer["tx_hash"],
                direction=direction,
                amount=transfer["amount"],
                block_timestamp=transfer["timestamp"],
            )
        )
        return True

    def _recompute_wallet_reputation(self, wallet: Wallet) -> None:
        txs = self.db.query(WalletTransaction).filter(WalletTransaction.wallet_id == wallet.id).all()

        by_coin: dict = {}
        for tx in txs:
            by_coin.setdefault(tx.coin_id, []).append(tx)

        positions = []
        for coin_id, coin_txs in by_coin.items():
            coin = self.db.query(Coin).filter(Coin.id == coin_id).first()
            if coin is None:
                continue
            ins = [t for t in coin_txs if t.direction == "in"]
            outs = [t for t in coin_txs if t.direction == "out"]
            if not ins:
                continue

            first_in = min(t.block_timestamp for t in ins)
            total_in = sum(t.amount for t in ins)
            total_out = sum(t.amount for t in outs)
            still_holding = (total_in - total_out) > HOLDING_EPSILON * max(total_in, 1)
            exited = total_out > HOLDING_EPSILON * max(total_in, 1)

            early_entry = False
            if coin.launch_time is not None:
                delta = (first_in - coin.launch_time).total_seconds() / 60
                early_entry = 0 <= delta <= settings.wallet_early_entry_window_minutes

            entry_price = self._nearest_price_at(coin_id, first_in)
            roi_pct = None
            if entry_price and entry_price > 0 and coin.price_usd is not None:
                roi_pct = (coin.price_usd - entry_price) / entry_price * 100

            hold_time_seconds = None
            if exited:
                last_out = max(t.block_timestamp for t in outs)
                hold_time_seconds = (last_out - first_in).total_seconds()

            positions.append(
                {
                    "still_holding": still_holding,
                    "early_entry": early_entry,
                    "roi_pct": roi_pct,
                    "hold_time_seconds": hold_time_seconds,
                }
            )

        self._apply_reputation(wallet, positions)

    def _apply_reputation(self, wallet: Wallet, positions: list[dict]) -> None:
        total_positions = len(positions)
        if total_positions == 0:
            return

        with_roi = [p for p in positions if p["roi_pct"] is not None]
        wins = sum(1 for p in with_roi if p["roi_pct"] > 0)
        win_rate = (wins / len(with_roi)) if with_roi else None
        avg_roi = statistics.mean(p["roi_pct"] for p in with_roi) if with_roi else None

        hold_times = [p["hold_time_seconds"] for p in positions if p["hold_time_seconds"] is not None]
        avg_hold = statistics.mean(hold_times) if hold_times else None

        early_count = sum(1 for p in positions if p["early_entry"])
        early_freq = early_count / total_positions

        wallet.total_positions = total_positions
        wallet.positions_with_known_roi = len(with_roi)
        wallet.wins = wins
        wallet.win_rate = win_rate
        wallet.avg_roi_pct = avg_roi
        wallet.avg_hold_time_seconds = avg_hold
        wallet.early_entry_count = early_count
        wallet.early_entry_frequency = early_freq
        wallet.reputation_score = self._reputation_score(win_rate, avg_roi, early_freq, total_positions)
        self.db.flush()

    def _reputation_score(
        self, win_rate: float | None, avg_roi: float | None, early_freq: float, total_positions: int
    ) -> float:
        """0-100. Weighted blend of win rate (40%), ROI magnitude (30%),
        early-entry frequency (20%), and a sample-size confidence term
        (10%) that keeps a wallet with one lucky trade from immediately
        outranking one with a longer track record. If we have no computable
        ROI at all (no price_history snapshot ever existed near any entry),
        falls back to a low-ceiling score based only on early-entry
        frequency and sample size, since the core signal is missing."""
        confidence = min(total_positions, 10) / 10 * 100

        if win_rate is None or avg_roi is None:
            return round(min(50.0, early_freq * 50 + confidence * 0.1), 1)

        win_component = win_rate * 100
        roi_clipped = max(-50.0, min(200.0, avg_roi))
        roi_component = (roi_clipped + 50) / 2.5  # maps [-50, 200] -> [0, 100]
        early_component = early_freq * 100

        score = 0.40 * win_component + 0.30 * roi_component + 0.20 * early_component + 0.10 * confidence
        return round(max(0.0, min(100.0, score)), 1)

    def _nearest_price_at(self, coin_id, ts: datetime) -> float | None:
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

    def _update_coin_wallet_score(self, coin: Coin) -> None:
        net_expr = func.sum(
            case((WalletTransaction.direction == "in", WalletTransaction.amount), else_=-WalletTransaction.amount)
        )
        holding_wallet_ids = (
            self.db.query(WalletTransaction.wallet_id)
            .filter(WalletTransaction.coin_id == coin.id)
            .group_by(WalletTransaction.wallet_id)
            .having(net_expr > HOLDING_EPSILON)
            .all()
        )
        ids = [w[0] for w in holding_wallet_ids]

        wallet_score = None
        if ids:
            reputations = (
                self.db.query(Wallet.reputation_score)
                .filter(Wallet.id.in_(ids), Wallet.reputation_score.isnot(None))
                .all()
            )
            values = [r[0] for r in reputations]
            if values:
                wallet_score = round(statistics.mean(values), 1)

        score = self.db.query(Score).filter(Score.coin_id == coin.id).first()
        if score is None:
            score = Score(coin_id=coin.id)
            self.db.add(score)
        score.wallet_score = wallet_score
        score.wallet_source = "evm"
        score.wallet_checked_at = datetime.utcnow()
        self.db.flush()

    def count_strong_holding_wallets(self, coin_id) -> int:
        """Used by AlertService for the 'multiple strong wallets accumulate
        a token' condition: currently-holding wallets, above the strong-
        reputation threshold, that entered within the lookback window."""
        # Timezone-AWARE cutoff is required here: r.first_in below comes
        # back from the DB as an offset-aware datetime (block_timestamp is
        # stored as DateTime(timezone=True)), and this comparison happens
        # in plain Python (on already-fetched rows), not inside a SQL
        # filter - unlike SQLAlchemy .filter() clauses elsewhere in this
        # file, Postgres never gets a chance to handle the tz conversion
        # here. Using datetime.utcnow() (naive) instead of
        # datetime.now(timezone.utc) caused every single coin checked by
        # this function to raise "can't compare offset-naive and
        # offset-aware datetimes" - found via real production logs
        # showing this exact exception on every coin, which was silently
        # making the whole alert cycle take far longer than it should
        # (thousands of failed per-coin attempts, not a stuck lock).
        cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.wallet_accumulation_lookback_hours)
        net_expr = func.sum(
            case((WalletTransaction.direction == "in", WalletTransaction.amount), else_=-WalletTransaction.amount)
        )
        first_in_expr = func.min(
            case((WalletTransaction.direction == "in", WalletTransaction.block_timestamp), else_=None)
        )
        rows = (
            self.db.query(WalletTransaction.wallet_id, net_expr.label("net"), first_in_expr.label("first_in"))
            .filter(WalletTransaction.coin_id == coin_id)
            .group_by(WalletTransaction.wallet_id)
            .having(net_expr > HOLDING_EPSILON)
            .all()
        )
        recent_holder_ids = [r.wallet_id for r in rows if r.first_in and r.first_in >= cutoff]
        if not recent_holder_ids:
            return 0

        return (
            self.db.query(Wallet)
            .filter(
                Wallet.id.in_(recent_holder_ids),
                Wallet.reputation_score >= settings.wallet_strong_reputation_threshold,
            )
            .count()
        )
