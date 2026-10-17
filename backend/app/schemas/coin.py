import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    narrative_score: float | None
    community_score: float | None
    wallet_score: float | None
    wallet_source: str | None
    risk_score: float | None
    liquidity_score: float | None
    trend_score: float | None
    overall_score: float | None
    confidence: float | None
    scoring_notes: str | None
    updated_at: datetime


class CoinOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    contract_address: str
    pair_address: str | None
    chain: str
    source: str
    symbol: str | None
    name: str | None
    launch_time: datetime | None
    liquidity_usd: float | None
    market_cap_usd: float | None
    fdv_usd: float | None
    volume_24h_usd: float | None
    price_usd: float | None
    price_change_1h: float | None
    price_change_24h: float | None
    is_active: bool
    first_seen_at: datetime
    last_updated_at: datetime


class CoinWithScoreOut(CoinOut):
    score: ScoreOut | None = None


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    coin_id: uuid.UUID
    coin_symbol: str | None = None
    coin_chain: str | None = None
    alert_type: str
    severity: str
    message: str
    trigger_value: float | None
    previous_value: float | None
    channels_delivered: str | None
    delivered: bool
    created_at: datetime


class CommunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lookback_days: int
    total_posts: int
    unique_posters: int
    engagement_total: float
    avg_engagement_per_post: float | None
    growth_rate_pct: float | None
    organic_discussion_ratio: float | None
    duplicate_content_ratio: float | None
    reddit_subscribers: int | None
    lunarcrush_galaxy_score: float | None
    data_source: str
    community_score: float | None
    updated_at: datetime


class NarrativeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    main_topic: str | None
    meme_category: str | None
    related_events: str | None
    similar_historical_memes: str | None
    emotion: str | None
    is_funny: bool | None
    is_controversial: bool | None
    is_relatable: bool | None
    could_spread_beyond_crypto: bool | None
    narrative_summary: str | None
    virality_score: float | None
    narrative_score: float | None
    post_count_analyzed: int
    sources_used: str | None
    updated_at: datetime


class SocialPostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source: str
    author: str | None
    text: str
    url: str | None
    engagement_score: float
    posted_at: datetime | None
    collected_at: datetime


class RiskFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    flag_type: str
    severity: str
    points: float
    description: str
    detected_at: datetime


class HistoricalScorePoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    overall_score: float
    liquidity_score: float | None
    trend_score: float | None
    recorded_at: datetime
