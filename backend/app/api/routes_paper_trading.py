from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.paper_trade import PaperTrade
from app.services.paper_trading_service import PaperTradingService
from app.workers.locks import task_lock

router = APIRouter(prefix="/api/paper-trading", tags=["paper-trading"])


@router.post("/run")
def run_paper_trading(db: Session = Depends(get_db)):
    """Manually trigger a paper trading check synchronously. Run this after
    /api/scoring/run so it's evaluating against fresh overall_score/risk_score
    data. Entirely simulated - no real money, no real wallet."""
    with task_lock("paper_trading_cycle") as acquired:
        if not acquired:
            return {"skipped": True, "reason": "a paper trading cycle (scheduled or manual) is already running"}
        service = PaperTradingService(db)
        return service.check_all_active()


@router.get("/trades")
def list_paper_trades(status: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    """List paper trades, optionally filtered by status ('open' or 'closed')."""
    query = db.query(PaperTrade)
    if status:
        query = query.filter(PaperTrade.status == status)
    trades = query.order_by(PaperTrade.created_at.desc()).limit(min(limit, 200)).all()
    return [
        {
            "id": str(t.id),
            "coin_id": str(t.coin_id),
            "symbol": t.symbol,
            "chain": t.chain,
            "position_size_gbp": t.position_size_gbp,
            "entry_price_usd": t.entry_price_usd,
            "entry_overall_score": t.entry_overall_score,
            "entry_risk_score": t.entry_risk_score,
            "entry_at": t.entry_at.isoformat() if t.entry_at else None,
            "exit_price_usd": t.exit_price_usd,
            "exit_at": t.exit_at.isoformat() if t.exit_at else None,
            "pnl_gbp": t.pnl_gbp,
            "pnl_pct": t.pnl_pct,
            "exit_reason": t.exit_reason,
            "status": t.status,
        }
        for t in trades
    ]


@router.get("/summary")
def paper_trading_summary(db: Session = Depends(get_db)):
    """Aggregate P&L stats - the actual answer to 'is this scoring system
    any good at picking winners'."""
    service = PaperTradingService(db)
    return service.get_summary()
