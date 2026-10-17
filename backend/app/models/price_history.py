import uuid
from datetime import datetime

from sqlalchemy import Float, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PriceHistory(Base):
    """Snapshot of a coin's key metrics at a point in time.
    Powers MODULE 6 (Trend Detection: velocity/acceleration/decay/momentum)."""

    __tablename__ = "price_history"
    __table_args__ = (Index("ix_price_history_coin_time", "coin_id", "recorded_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("coins.id"), nullable=False)

    price_usd: Mapped[float] = mapped_column(Float, nullable=True)
    liquidity_usd: Mapped[float] = mapped_column(Float, nullable=True)
    market_cap_usd: Mapped[float] = mapped_column(Float, nullable=True)
    volume_24h_usd: Mapped[float] = mapped_column(Float, nullable=True)

    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    coin = relationship("Coin", back_populates="price_history")
