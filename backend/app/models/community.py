import uuid
from datetime import datetime

from sqlalchemy import Float, Integer, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Community(Base):
    """MODULE 4: Community Intelligence - one row per coin, overwritten each
    analysis cycle (a current snapshot, not a history - like Narrative).

    Deliberately built as an *analysis layer over data MODULE 2 already
    collects* (SocialPost rows from Reddit/CryptoPanic/X) rather than a
    separate collection pipeline - see community_service.py docstring for
    why, and for exactly what each metric here does and doesn't measure.
    """

    __tablename__ = "communities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("coins.id"), nullable=False, unique=True)

    lookback_days: Mapped[int] = mapped_column(Integer, default=7)
    total_posts: Mapped[int] = mapped_column(Integer, default=0)
    unique_posters: Mapped[int] = mapped_column(Integer, default=0)
    engagement_total: Mapped[float] = mapped_column(Float, default=0.0)
    avg_engagement_per_post: Mapped[float] = mapped_column(Float, nullable=True)

    growth_rate_pct: Mapped[float] = mapped_column(Float, nullable=True)  # vs prior equal-length window
    organic_discussion_ratio: Mapped[float] = mapped_column(Float, nullable=True)  # unique_posters / total_posts
    duplicate_content_ratio: Mapped[float] = mapped_column(Float, nullable=True)  # spam proxy, 0-1

    reddit_subscribers: Mapped[int] = mapped_column(Integer, nullable=True)  # "Followers" proxy, Reddit only
    lunarcrush_galaxy_score: Mapped[float] = mapped_column(Float, nullable=True)  # 0-100, from LunarCrush if matched
    data_source: Mapped[str] = mapped_column(String, default="posts")  # "posts" | "lunarcrush" | "posts+lunarcrush"

    community_score: Mapped[float] = mapped_column(Float, nullable=True)  # 0-100, feeds Score.community_score

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    coin = relationship("Coin", back_populates="community")
