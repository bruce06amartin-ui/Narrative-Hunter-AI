import uuid
from datetime import datetime

from sqlalchemy import Float, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PaperTrade(Base):
    """A simulated (hypothetical) trade - no real money, no real wallet.

    Entry rule: overall_score crosses from below to at/above
    PAPER_TRADING_ENTRY_SCORE_THRESHOLD, AND risk_score is either
    unavailable (null - not yet checked) or below
    PAPER_TRADING_RISK_GATE_MAX. Only one open position per coin at a time
    - a coin that's already been "bought" won't be bought again while that
    position is still open, even if it keeps re-crossing the threshold.

    Exit rule: current price >= entry_price * (1 + PAPER_TRADING_EXIT_GAIN_PCT/100).
    No stop-loss is implemented - a position stays open indefinitely until
    it hits the target gain, however long that takes (or never happens).
    This is a deliberate simplification for a v1: it means a simulated
    position can show a large paper LOSS while still technically "open" and
    waiting for the target, which is itself useful information about the
    scoring system's real-world hit rate.
    """

    __tablename__ = "paper_trades"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("coins.id"), index=True)

    # Snapshotted at entry time, so this row is still meaningful even if the
    # coin's symbol/chain later changes or the coin is deactivated.
    symbol: Mapped[str] = mapped_column(String)
    chain: Mapped[str] = mapped_column(String)

    position_size_gbp: Mapped[float] = mapped_column(Float)
    entry_price_usd: Mapped[float] = mapped_column(Float)
    entry_overall_score: Mapped[float] = mapped_column(Float)
    entry_risk_score: Mapped[float] = mapped_column(Float, nullable=True)
    entry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    exit_price_usd: Mapped[float] = mapped_column(Float, nullable=True)
    exit_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    pnl_gbp: Mapped[float] = mapped_column(Float, nullable=True)
    pnl_pct: Mapped[float] = mapped_column(Float, nullable=True)
    exit_reason: Mapped[str] = mapped_column(String, nullable=True)  # "take_profit" | "stop_loss" | "max_hold_timeout"

    status: Mapped[str] = mapped_column(String, default="open")  # "open" | "closed"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    coin = relationship("Coin")
