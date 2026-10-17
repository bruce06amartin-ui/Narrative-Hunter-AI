"""
MODULE 3 extension: Solana Wallet Intelligence.

Previously MODULE 3 was EVM-only (eth, base) - this closes that gap for
Solana, the majority chain in most meme-coin discovery data.

APPROACH, AND AN HONEST DIFFERENCE FROM THE EVM VERSION: this uses Solana
Tracker's top-holders endpoint to find who currently holds a coin, then
their per-token realized/unrealized PnL for that SAME coin. This is
DIFFERENT in kind from the EVM wallet module, which aggregates a wallet's
track record ACROSS every coin this platform tracks (a genuine external
reputation signal - "do historically good wallets hold this"). Here, we
only know how a wallet has done on THIS ONE coin - which is naturally
correlated with the coin's own price performance (if price went up,
current holders are trivially in profit). This is still a real, useful
signal (it requires wallets to still be holding, not just price moving,
and concentrated-holder profit can be a genuine risk signal - deeply
profitable large holders may be more likely to sell), but it is NOT
independent of trend_score the way EVM's wallet_score is independent of
Solana's own trend data. Treat it as a real but imperfect signal,
documented honestly rather than oversold.

BUDGET: see config.py's solana_wallet_* settings for the worked-out
request math against Solana Tracker's REAL free tier (2,500/month,
confirmed via their actual pricing page - an earlier version of this
mistakenly cited 10,000/month from a search result). Bounded the
same way as risk/wallet/price-refresh: only new-or-stale coins get
checked each cycle (solana_wallet_recheck_hours), and only up to
solana_wallet_max_coins_per_cycle coins per cycle, prioritized by
liquidity.

Writes to the SAME Score.wallet_score / Score.wallet_checked_at fields the
EVM module uses - gated by chain, so a coin only ever gets processed by
one of the two wallet-intelligence paths, never both.
"""

import logging
import statistics
from datetime import datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.collectors.solanatracker import SolanaTrackerCollector
from app.config import settings
from app.models.coin import Coin
from app.models.score import Score
from app.services.liquidity_sanity import MANIPULATION_CHECK_MIN_LIQUIDITY_USD, MIN_VOLUME_TO_LIQUIDITY_RATIO

logger = logging.getLogger(__name__)


class SolanaWalletIntelligenceService:
    def __init__(self, db: Session):
        self.db = db
        self.collector = SolanaTrackerCollector()

    def check_all_active(self) -> dict:
        if not self.collector.is_configured():
            return {
                "skipped": True,
                "reason": "SOLANATRACKER_API_KEY not configured",
                "ran_at": datetime.utcnow().isoformat(),
            }

        total_solana_active = (
            self.db.query(Coin).filter(Coin.is_active.is_(True), Coin.chain == "solana").count()
        )

        recheck_cutoff = datetime.utcnow() - timedelta(hours=settings.solana_wallet_recheck_hours)
        coins = (
            self.db.query(Coin)
            .outerjoin(Score, Score.coin_id == Coin.id)
            .filter(
                Coin.is_active.is_(True),
                Coin.chain == "solana",
                (Score.id.is_(None))
                | (Score.wallet_checked_at.is_(None))
                | (Score.wallet_checked_at < recheck_cutoff),
                # Manipulation sanity check: a real pool with genuinely
                # large liquidity should see meaningful trading volume
                # relative to that size. A coin claiming huge liquidity
                # with near-zero volume is a known DeFi pattern (fake
                # reserves reported to indexers to appear significant to
                # bots/scanners) - confirmed via real production data: a
                # coin showing $180M liquidity had only $2,099 in 24h
                # volume, an ~86,000:1 ratio that's essentially impossible
                # for genuine activity. Without this filter, our tiny,
                # tightly-budgeted request allowance (see config.py) would
                # get spent checking manipulated entries first, since the
                # query orders by liquidity descending, ahead of coins
                # with real, plausible trading behind their numbers.
                or_(
                    Coin.liquidity_usd < MANIPULATION_CHECK_MIN_LIQUIDITY_USD,
                    Coin.volume_24h_usd.is_(None),
                    Coin.volume_24h_usd >= Coin.liquidity_usd * MIN_VOLUME_TO_LIQUIDITY_RATIO,
                ),
            )
            # Same reasoning as narrative_scanner_service.py's identical
            # change: prioritize by CURRENT overall_score rather than raw
            # liquidity, concentrating this tightly-budgeted signal on
            # coins already strong elsewhere and genuinely close to
            # crossing 70, not just whichever coins are biggest.
            .order_by(func.coalesce(Score.overall_score, -1).desc())
            .limit(settings.solana_wallet_max_coins_per_cycle)
            .all()
        )

        processed = 0
        for coin in coins:
            coin_id_for_logging = coin.id
            try:
                self._process_coin(coin)
                self.db.commit()
                processed += 1
            except Exception:  # noqa: BLE001 - one bad coin shouldn't kill the run
                self.db.rollback()
                logger.exception("Solana wallet check failed for coin id=%s", coin_id_for_logging)

        return {
            "coins_processed": processed,
            "due_for_check_this_cycle": len(coins),
            "total_solana_active": total_solana_active,
            "ran_at": datetime.utcnow().isoformat(),
        }

    def _process_coin(self, coin: Coin) -> None:
        holders = self.collector.get_top_holders(
            coin.contract_address, limit=settings.solana_wallet_holders_per_coin
        )

        reputations: list[float] = []
        for holder in holders:
            pnl = self.collector.get_wallet_token_pnl(holder["address"], coin.contract_address)
            if pnl is None:
                continue
            reputations.append(self._reputation_score(pnl))

        wallet_score = round(statistics.mean(reputations), 1) if reputations else None

        score = self.db.query(Score).filter(Score.coin_id == coin.id).first()
        if score is None:
            score = Score(coin_id=coin.id)
            self.db.add(score)
        score.wallet_score = wallet_score
        score.wallet_source = "solana"
        score.wallet_checked_at = datetime.utcnow()
        self.db.flush()

    def _reputation_score(self, pnl: dict) -> float:
        """0-100. Simpler than the EVM version by necessity (see module
        docstring for why): primarily reflects whether this specific
        holder is currently in profit on this specific coin, weighted by
        ROI magnitude. A holder with no computable ROI (API had partial
        data) gets a neutral 50 rather than being excluded entirely -
        they're a confirmed real holder, just with incomplete PnL data."""
        roi_pct = pnl.get("roi_pct")
        total_pnl = pnl.get("total_pnl_usd")

        if roi_pct is None and total_pnl is None:
            return 50.0

        if roi_pct is not None:
            # Breakeven-centered: 0% ROI -> 50 (neutral), -100% -> 0,
            # +100% or more -> 100. Clipped symmetrically so a huge gain
            # doesn't need to be distinguished from a merely-large one -
            # both represent "this holder is clearly winning."
            roi_clipped = max(-100.0, min(100.0, roi_pct))
            return round(max(0.0, min(100.0, (roi_clipped + 100) / 2)), 1)

        return 65.0 if total_pnl > 0 else 35.0
