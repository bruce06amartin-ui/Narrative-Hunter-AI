import uuid
from datetime import datetime

from sqlalchemy import String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Alert(Base):
    """MODULE 9: Alerts - one row per triggered notification.

    alert_type is one of the conditions AlertService currently evaluates
    (see app/services/alert_service.py for the full list and which spec
    conditions are implemented vs. pending). channels_delivered records
    which of Discord/Telegram/Email actually sent successfully - a channel
    only appears here if it was configured AND the send succeeded, so a
    misconfigured/absent channel doesn't silently look like it worked.
    """

    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("coins.id"), nullable=False, index=True)

    alert_type: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "overall_score_threshold"
    severity: Mapped[str] = mapped_column(String, nullable=False)  # "info" | "warning" | "critical"
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Snapshot of the values that triggered this alert, for audit/debugging.
    trigger_value: Mapped[float] = mapped_column(Float, nullable=True)
    previous_value: Mapped[float] = mapped_column(Float, nullable=True)

    channels_delivered: Mapped[str] = mapped_column(String, nullable=True)  # comma-separated: "discord,telegram"
    delivery_error: Mapped[str] = mapped_column(Text, nullable=True)
    delivered: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    coin = relationship("Coin", back_populates="alerts")

    def __repr__(self) -> str:
        return f"<Alert {self.alert_type} coin_id={self.coin_id} delivered={self.delivered}>"
