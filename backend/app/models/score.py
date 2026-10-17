import uuid
from datetime import datetime

from sqlalchemy import Float, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Score(Base):
    """MODULE 8: current/latest Overall Opportunity Score for a coin.

    NOTE: liquidity_score, trend_score, wallet_score, risk_score,
    narrative_score, and community_score are all actively computed - see
    scoring_service.py for how they combine into overall_score. This is now
    the full MODULE 8 spec (Narrative/Community/Wallets/Risk/Liquidity/Trend).
    """

    __tablename__ = "scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("coins.id"), nullable=False, unique=True)

    narrative_score: Mapped[float] = mapped_column(Float, nullable=True)   # MODULE 2 / 7 - not yet implemented
    community_score: Mapped[float] = mapped_column(Float, nullable=True)  # MODULE 4 - not yet implemented
    wallet_score: Mapped[float] = mapped_column(Float, nullable=True)     # MODULE 3 - not yet implemented
    risk_score: Mapped[float] = mapped_column(Float, nullable=True)       # MODULE 5 - implemented
    # Dedicated field so RiskService's specific reasoning (e.g. "No risk
    # data available from GoPlus for this chain/token yet" vs "N risk
    # flag(s) detected") survives being overwritten by ScoringService's own
    # generic composed text - previously both wrote to the same
    # scoring_notes field, so whichever service ran most recently silently
    # won, hiding the more specific/accurate message underneath.
    risk_notes: Mapped[str] = mapped_column(Text, nullable=True)
    # When RiskService last actually checked this coin (success OR no-data
    # from GoPlus) - lets check_all_active() only re-check coins that are
    # new or stale, instead of blindly re-scanning every active coin every
    # cycle. Without this, a full pass through N coins (each throttled to
    # ~2/sec against GoPlus) takes roughly N/2 seconds - at real scale
    # (1000+ coins) that's longer than the default scheduling interval,
    # so cycles perpetually overlap and never reliably catch up. Found via
    # real production data: a coin could go 18+ hours without ever
    # completing a risk check, purely from this throughput mismatch.
    risk_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    # Same rationale as risk_checked_at - WalletIntelligenceService also
    # makes one throttled external call (Etherscan) per EVM coin, every
    # cycle, and has the identical throughput-vs-interval risk at scale.
    wallet_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    # Transparency field, same pattern as Community.data_source - EVM
    # wallet_score (cross-coin reputation, via Etherscan) and Solana
    # wallet_score (single-coin PnL, via Solana Tracker) are genuinely
    # different measurements sharing one field. "evm" | "solana" | null.
    wallet_source: Mapped[str] = mapped_column(String, nullable=True)
    # Same rationale again - DiscoveryService.refresh_existing_prices() also
    # calls a throttled external API (GeckoTerminal) across potentially
    # every active coin, and real logs showed even a single 30-address
    # batch call needs real pacing (429s observed) - the same overlap risk
    # applies at scale unless bounded the same way.
    price_refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    # Same rationale again - narrative scanning (free Telegram/RSS
    # collection, separate from the AI-analysis spend cap) also needs
    # bounding at scale to avoid the same overlap risk.
    narrative_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    youtube_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    liquidity_score: Mapped[float] = mapped_column(Float, nullable=True)  # implemented
    trend_score: Mapped[float] = mapped_column(Float, nullable=True)      # implemented

    overall_score: Mapped[float] = mapped_column(Float, nullable=True, index=True)
    # 0.0-1.0, how much of the full signal set was actually confirmed when
    # overall_score was computed - already calculated in
    # ScoringService._weighted_average_with_confidence, just never
    # persisted before. Lets the dashboard show "58, but only 17%
    # confidence" at a glance instead of requiring the raw scoring_notes
    # text to be parsed for this.
    confidence: Mapped[float] = mapped_column(Float, nullable=True)
    scoring_notes: Mapped[str] = mapped_column(Text, nullable=True)  # which signals were available/missing

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    coin = relationship("Coin", back_populates="scores")


class HistoricalScore(Base):
    """Time series of scores so the dashboard can chart momentum over time,
    and so MODULE 9 (Alerts) can detect threshold crossings / score deltas
    between consecutive cycles without needing separate cooldown tracking."""

    __tablename__ = "historical_scores"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("coins.id"), nullable=False)

    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    liquidity_score: Mapped[float] = mapped_column(Float, nullable=True)
    trend_score: Mapped[float] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=True)
    narrative_score: Mapped[float] = mapped_column(Float, nullable=True)
    community_score: Mapped[float] = mapped_column(Float, nullable=True)

    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    coin = relationship("Coin", back_populates="historical_scores")
