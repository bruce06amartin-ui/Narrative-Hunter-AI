import uuid
from datetime import datetime

from sqlalchemy import String, Float, Text, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Narrative(Base):
    """MODULE 2 (Narrative Scanner) + MODULE 7 (Narrative AI) combined output.

    Produced by NarrativeAIService from a batch of SocialPost rows via a
    single Claude call (see narrative_ai_service.py). One row per coin,
    overwritten each time the coin is re-analyzed - this is a current
    snapshot, not a history (unlike scores/historical_scores).
    """

    __tablename__ = "narratives"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("coins.id"), nullable=False, unique=True)

    main_topic: Mapped[str] = mapped_column(String, nullable=True)
    meme_category: Mapped[str] = mapped_column(String, nullable=True)
    related_events: Mapped[str] = mapped_column(Text, nullable=True)
    similar_historical_memes: Mapped[str] = mapped_column(Text, nullable=True)

    emotion: Mapped[str] = mapped_column(String, nullable=True)
    is_funny: Mapped[bool] = mapped_column(Boolean, nullable=True)
    is_controversial: Mapped[bool] = mapped_column(Boolean, nullable=True)
    is_relatable: Mapped[bool] = mapped_column(Boolean, nullable=True)
    could_spread_beyond_crypto: Mapped[bool] = mapped_column(Boolean, nullable=True)

    narrative_summary: Mapped[str] = mapped_column(Text, nullable=True)
    virality_score: Mapped[float] = mapped_column(Float, nullable=True)   # MODULE 7 output, 0-100
    narrative_score: Mapped[float] = mapped_column(Float, nullable=True)  # MODULE 2 output, 0-100 (feeds Score.narrative_score)

    post_count_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    sources_used: Mapped[str] = mapped_column(String, nullable=True)  # comma-separated

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    coin = relationship("Coin", back_populates="narrative")
