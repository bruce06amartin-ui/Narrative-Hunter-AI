import uuid
from datetime import datetime

from sqlalchemy import String, Float, Integer, DateTime, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Wallet(Base):
    """MODULE 3: Wallet Intelligence - aggregate reputation for one address.

    Metrics are computed only from coins THIS platform has discovered and
    tracked - not a wallet's full trading history (we have no way to see
    that). A wallet with a high reputation_score here means "has a good
    track record on the coins we've been watching," not "is a proven
    trader in general." See wallet_service.py for the full list of
    approximations (entry-price proxy, hold-time definition, etc).
    """

    __tablename__ = "wallets"
    __table_args__ = (
        UniqueConstraint("chain", "address", name="uq_wallet_chain_address"),
        Index("ix_wallets_reputation", "reputation_score"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chain: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[str] = mapped_column(String, nullable=False, index=True)

    total_positions: Mapped[int] = mapped_column(Integer, default=0)  # distinct coins with an 'in' tx
    positions_with_known_roi: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, nullable=True)  # wins / positions_with_known_roi
    avg_roi_pct: Mapped[float] = mapped_column(Float, nullable=True)
    avg_hold_time_seconds: Mapped[float] = mapped_column(Float, nullable=True)
    early_entry_count: Mapped[int] = mapped_column(Integer, default=0)
    early_entry_frequency: Mapped[float] = mapped_column(Float, nullable=True)
    reputation_score: Mapped[float] = mapped_column(Float, nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    transactions = relationship("WalletTransaction", back_populates="wallet", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Wallet {self.chain}:{self.address[:10]} rep={self.reputation_score}>"
