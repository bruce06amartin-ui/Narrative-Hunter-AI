"""
Paper Trading Service (not part of the original 10-module spec - added to
test whether the scoring system is actually any good at picking winners,
with zero real money at risk before ever considering real execution).

ENTRY RULE: a coin's overall_score crosses from below to at/above
PAPER_TRADING_ENTRY_SCORE_THRESHOLD (default 70), using the same
consecutive-HistoricalScore crossing-detection pattern as MODULE 9's
alerts - AND risk_score is either unavailable (null, not yet checked) or
below PAPER_TRADING_RISK_GATE_MAX (default 60). Only one open position per
coin at a time: a coin that's already been "bought" here won't be bought
again while that position is still open, even if it dips below and
re-crosses the threshold again.

EXIT RULE: current price >= entry_price * (1 + PAPER_TRADING_EXIT_GAIN_PCT/100)
(default +25%). No stop-loss - a position stays open indefinitely until it
hits the target, however long that takes. This is a deliberate v1
simplification: it means a simulated position can show a large paper LOSS
while technically still "open," which is itself useful information about
how often (and how badly) the entry signal gets it wrong, not just how
often it gets it right.

This is entirely hypothetical: no wallet, no real transaction, no real
money. Position size is a fixed PAPER_TRADING_POSITION_SIZE_GBP (default
50 GBP) per trade, used only to express P&L in real currency terms for
readability.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models.coin import Coin
from app.models.paper_trade import PaperTrade
from app.models.score import HistoricalScore, Score

logger = logging.getLogger(__name__)


class PaperTradingService:
    def __init__(self, db: Session):
        self.db = db

    def check_all_active(self) -> dict:
        # Filtered down from "every active coin" (7,500+, confirmed via
        # live production data) to only coins that could actually matter
        # this cycle: either already clearing the entry score threshold
        # (the same condition _maybe_enter itself requires), or already
        # holding an open position that needs its exit checked regardless
        # of what its current score is. Real performance fix found via
        # live diagnosis (Celery `inspect active` + pg_stat_activity):
        # processing all 7,500+ coins individually, with a separate
        # commit per coin, was taking 12+ minutes per cycle under real
        # concurrent load - not a hang, just genuinely unfiltered work at
        # a scale this project has grown well past.
        open_coin_ids = (
            self.db.query(PaperTrade.coin_id).filter(PaperTrade.status == "open").subquery()
        )
        coins = (
            self.db.query(Coin)
            .outerjoin(Score, Score.coin_id == Coin.id)
            .filter(
                Coin.is_active.is_(True),
                (Score.overall_score >= settings.paper_trading_entry_score_threshold)
                | (Coin.id.in_(open_coin_ids)),
            )
            .all()
        )
        entries_opened = 0
        exits_closed = 0
        for coin in coins:
            coin_id_for_logging = coin.id
            try:
                if self._maybe_enter(coin):
                    entries_opened += 1
                if self._maybe_exit(coin):
                    exits_closed += 1
                self.db.commit()
            except Exception:  # noqa: BLE001 - one bad coin shouldn't kill the run
                self.db.rollback()
                logger.exception("Paper trading check failed for coin id=%s", coin_id_for_logging)

        return {
            "entries_opened": entries_opened,
            "exits_closed": exits_closed,
            "candidates_checked": len(coins),
            "ran_at": datetime.utcnow().isoformat(),
        }

    def _maybe_enter(self, coin: Coin) -> bool:
        existing_open = (
            self.db.query(PaperTrade)
            .filter(PaperTrade.coin_id == coin.id, PaperTrade.status == "open")
            .first()
        )
        if existing_open:
            return False

        recent = (
            self.db.query(HistoricalScore)
            .filter(HistoricalScore.coin_id == coin.id)
            .order_by(HistoricalScore.recorded_at.desc())
            .limit(2)
            .all()
        )
        if len(recent) < 2:
            return False

        current, previous = recent[0], recent[1]
        threshold = settings.paper_trading_entry_score_threshold

        crossed_up = (
            current.overall_score is not None
            and current.overall_score >= threshold
            and (previous.overall_score is None or previous.overall_score < threshold)
        )
        if not crossed_up:
            return False

        risk_score = current.risk_score
        risk_gate_passed = risk_score is None or risk_score < settings.paper_trading_risk_gate_max
        if not risk_gate_passed:
            logger.info(
                "Paper trade entry skipped for coin id=%s: overall_score crossed %.0f but risk_score=%.0f "
                "(gate is %.0f)",
                coin.id, threshold, risk_score, settings.paper_trading_risk_gate_max,
            )
            return False

        if coin.price_usd is None or coin.price_usd <= 0:
            return False

        trade = PaperTrade(
            coin_id=coin.id,
            symbol=coin.symbol or coin.name or "UNKNOWN",
            chain=coin.chain,
            position_size_gbp=settings.paper_trading_position_size_gbp,
            entry_price_usd=coin.price_usd,
            entry_overall_score=current.overall_score,
            entry_risk_score=risk_score,
            entry_at=datetime.utcnow(),
            status="open",
        )
        self.db.add(trade)
        self.db.flush()
        logger.info(
            "Paper trade OPENED: %s (%s) at $%.8f, overall_score=%.0f, risk_score=%s",
            trade.symbol, trade.chain, trade.entry_price_usd, trade.entry_overall_score,
            f"{risk_score:.0f}" if risk_score is not None else "n/a",
        )
        return True

    def _maybe_exit(self, coin: Coin) -> bool:
        open_trade = (
            self.db.query(PaperTrade)
            .filter(PaperTrade.coin_id == coin.id, PaperTrade.status == "open")
            .first()
        )
        if not open_trade:
            return False
        if coin.price_usd is None or coin.price_usd <= 0:
            return False

        gain_pct = ((coin.price_usd - open_trade.entry_price_usd) / open_trade.entry_price_usd) * 100

        hold_cutoff = open_trade.entry_at + timedelta(hours=settings.paper_trading_max_hold_hours)
        timed_out = datetime.utcnow() >= hold_cutoff

        # Check in this order: a real trader would take a hit target
        # before either of the other two even become relevant, so this
        # ordering matches what would actually happen, not just code
        # convenience.
        if gain_pct >= settings.paper_trading_exit_gain_pct:
            exit_reason = "take_profit"
        elif gain_pct <= settings.paper_trading_stop_loss_pct:
            exit_reason = "stop_loss"
        elif timed_out:
            exit_reason = "max_hold_timeout"
        else:
            return False  # still genuinely open - none of the three exit conditions have fired

        pnl_gbp = open_trade.position_size_gbp * (gain_pct / 100)

        open_trade.exit_price_usd = coin.price_usd
        open_trade.exit_at = datetime.utcnow()
        open_trade.pnl_pct = gain_pct
        open_trade.pnl_gbp = pnl_gbp
        open_trade.exit_reason = exit_reason
        open_trade.status = "closed"
        self.db.flush()
        logger.info(
            "Paper trade CLOSED (%s): %s (%s) at $%.8f, gain=%.1f%%, pnl=%.2f GBP",
            exit_reason, open_trade.symbol, open_trade.chain, coin.price_usd, gain_pct, pnl_gbp,
        )
        return True

    def get_summary(self) -> dict:
        all_trades = self.db.query(PaperTrade).all()
        closed = [t for t in all_trades if t.status == "closed"]
        open_trades = [t for t in all_trades if t.status == "open"]

        total_realized_pnl_gbp = sum(t.pnl_gbp for t in closed if t.pnl_gbp is not None)
        win_count = sum(1 for t in closed if t.pnl_gbp is not None and t.pnl_gbp > 0)
        closed_by_take_profit = sum(1 for t in closed if t.exit_reason == "take_profit")
        closed_by_stop_loss = sum(1 for t in closed if t.exit_reason == "stop_loss")
        closed_by_timeout = sum(1 for t in closed if t.exit_reason == "max_hold_timeout")

        unrealized_pnl_gbp = 0.0
        for t in open_trades:
            coin = self.db.query(Coin).filter(Coin.id == t.coin_id).first()
            if coin and coin.price_usd:
                pct = ((coin.price_usd - t.entry_price_usd) / t.entry_price_usd) * 100
                unrealized_pnl_gbp += t.position_size_gbp * (pct / 100)

        return {
            "total_trades": len(all_trades),
            "open_positions": len(open_trades),
            "closed_positions": len(closed),
            "win_count": win_count,
            "win_rate_pct": round((win_count / len(closed)) * 100, 1) if closed else None,
            "closed_by_take_profit": closed_by_take_profit,
            "closed_by_stop_loss": closed_by_stop_loss,
            "closed_by_timeout": closed_by_timeout,
            "total_realized_pnl_gbp": round(total_realized_pnl_gbp, 2),
            "total_unrealized_pnl_gbp": round(unrealized_pnl_gbp, 2),
            "total_pnl_gbp": round(total_realized_pnl_gbp + unrealized_pnl_gbp, 2),
            # Exposed specifically so the frontend can render the real,
            # current rules instead of a hardcoded string - a hardcoded
            # "crosses 70" description text drifted out of sync with the
            # real threshold twice already (70->65->64) before this fix.
            "entry_score_threshold": settings.paper_trading_entry_score_threshold,
            "risk_gate_max": settings.paper_trading_risk_gate_max,
            "exit_gain_pct": settings.paper_trading_exit_gain_pct,
            "stop_loss_pct": settings.paper_trading_stop_loss_pct,
            "max_hold_hours": settings.paper_trading_max_hold_hours,
        }
