import uuid
from datetime import datetime

from sqlalchemy import String, Float, Text, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SocialPost(Base):
    """MODULE 2: Narrative Scanner - one ingested post/article mentioning a coin."""

    __tablename__ = "social_posts"
    __table_args__ = (
        UniqueConstraint("source", "external_id", "coin_id", name="uq_social_post_source_external"),
        Index("ix_social_posts_coin_source", "coin_id", "source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("coins.id"), nullable=False)

    source: Mapped[str] = mapped_column(String, nullable=False)  # "reddit" | "cryptopanic" | "twitter"
    external_id: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str] = mapped_column(String, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=True)
    engagement_score: Mapped[float] = mapped_column(Float, default=0.0)
    community: Mapped[str] = mapped_column(String, nullable=True)  # e.g. subreddit name, for Reddit posts

    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    coin = relationship("Coin", back_populates="social_posts")
