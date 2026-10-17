import uuid
from datetime import datetime

from sqlalchemy import String, Float, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WalletTransaction(Base):
    """MODULE 3: one ingested ERC20 transfer event, from a wallet's
    perspective. direction='in' means this wallet received tokens
    (a proxy for "bought"); direction='out' means it sent tokens (a proxy
    for "sold" - though it could also just be a transfer to another wallet
    the holder controls; there's no way to distinguish that from a real
    DEX sell using transfer data alone. See wallet_service.py.

    A single on-chain transfer (one tx_hash) produces up to two rows: one
    for the receiving wallet (direction='in') and one for the sending
    wallet (direction='out') - unless one side is the coin's own known
    pair_address, which is skipped so the AMM pool itself doesn't get
    scored as a "wallet."
    """

    __tablename__ = "wallet_transactions"
    __table_args__ = (
        UniqueConstraint("tx_hash", "wallet_id", "direction", name="uq_wallet_tx_direction"),
        Index("ix_wallet_tx_wallet_coin", "wallet_id", "coin_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wallet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=False)
    coin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("coins.id"), nullable=False)

    tx_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String, nullable=False)  # "in" | "out"
    amount: Mapped[float] = mapped_column(Float, nullable=False)  # decimals-adjusted token amount

    block_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    wallet = relationship("Wallet", back_populates="transactions")
    coin = relationship("Coin", back_populates="wallet_transactions")
