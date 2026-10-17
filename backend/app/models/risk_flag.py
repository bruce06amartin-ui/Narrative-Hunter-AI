import uuid
from datetime import datetime

from sqlalchemy import String, Float, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RiskFlag(Base):
    """MODULE 5: Rug Detection - one row per specific finding on a coin.

    Kept separate from the aggregate Score.risk_score so the dashboard can
    show *why* a coin is risky, not just a number. Re-computed fresh each
    risk-check cycle: old flags for a coin are cleared and replaced rather
    than accumulated, since what matters is current state (e.g. "mint
    authority active right now"), not history of past checks.
    """

    __tablename__ = "risk_flags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("coins.id"), nullable=False, index=True)

    flag_type: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "mint_authority_active"
    severity: Mapped[str] = mapped_column(String, nullable=False)  # "low" | "medium" | "high" | "critical"
    points: Mapped[float] = mapped_column(Float, nullable=False)  # contribution to risk_score (0-100 scale)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    coin = relationship("Coin", back_populates="risk_flags")

    def __repr__(self) -> str:
        return f"<RiskFlag {self.flag_type} ({self.severity}) coin_id={self.coin_id}>"
