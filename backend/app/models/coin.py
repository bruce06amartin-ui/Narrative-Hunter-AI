import uuid
from datetime import datetime

from sqlalchemy import String, Float, DateTime, Boolean, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Coin(Base):
    """MODULE 1: Coin Discovery Service storage."""

    __tablename__ = "coins"
    __table_args__ = (
        UniqueConstraint("chain", "contract_address", name="uq_chain_contract"),
        Index("ix_coins_chain_launch_time", "chain", "launch_time"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    contract_address: Mapped[str] = mapped_column(String, nullable=False, index=True)
    pair_address: Mapped[str] = mapped_column(String, nullable=True, index=True)
    chain: Mapped[str] = mapped_column(String, nullable=False, index=True)  # solana / eth / base ...
    source: Mapped[str] = mapped_column(String, nullable=False)  # geckoterminal / dexscreener / pump.fun ...

    symbol: Mapped[str] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=True)

    launch_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    liquidity_usd: Mapped[float] = mapped_column(Float, nullable=True)
    market_cap_usd: Mapped[float] = mapped_column(Float, nullable=True)
    fdv_usd: Mapped[float] = mapped_column(Float, nullable=True)
    volume_24h_usd: Mapped[float] = mapped_column(Float, nullable=True)

    price_usd: Mapped[float] = mapped_column(Float, nullable=True)
    price_change_1h: Mapped[float] = mapped_column(Float, nullable=True)
    price_change_24h: Mapped[float] = mapped_column(Float, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Enrichment (MODULE 2/5): fetched opportunistically, not on every cycle
    telegram_handle: Mapped[str] = mapped_column(String, nullable=True)
    twitter_handle: Mapped[str] = mapped_column(String, nullable=True)
    social_enrichment_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    pool_migration_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    creator_address: Mapped[str] = mapped_column(String, nullable=True, index=True)  # from GoPlus, for repeat-deployer detection

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    price_history = relationship("PriceHistory", back_populates="coin", cascade="all, delete-orphan")
    scores = relationship("Score", back_populates="coin", cascade="all, delete-orphan")
    historical_scores = relationship("HistoricalScore", back_populates="coin", cascade="all, delete-orphan")
    risk_flags = relationship("RiskFlag", back_populates="coin", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="coin", cascade="all, delete-orphan")
    wallet_transactions = relationship("WalletTransaction", back_populates="coin", cascade="all, delete-orphan")
    social_posts = relationship("SocialPost", back_populates="coin", cascade="all, delete-orphan")
    narrative = relationship("Narrative", back_populates="coin", uselist=False, cascade="all, delete-orphan")
    community = relationship("Community", back_populates="coin", uselist=False, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Coin {self.symbol} {self.chain}:{self.contract_address[:8]}>"
