"""
MODULE 4: Community Intelligence.

Deliberately built as an ANALYSIS LAYER over data MODULE 2 already collects
(SocialPost rows from Reddit/CryptoPanic/X), not a separate collection
pipeline. Running a second, independent collection pass for "community"
metrics would mean hitting the same rate-limited/paid APIs twice for
largely overlapping data - this reuses what's already in the database.
Practical implication: run this AFTER NarrativeScannerService in a given
cycle, and if no narrative sources are configured, community metrics simply
won't have any posts to analyze either.

Metric definitions and what they don't measure:
  - LunarCrush:    optional bonus source (LUNARCRUSH_API_KEY, free tier is
                   4 requests/minute - see collectors/lunarcrush.py for why
                   that's not actually limiting, given it's a bulk endpoint).
                   Used two ways: (1) FALLBACK - if our own post-collection
                   found nothing for a coin but LunarCrush already tracks
                   it, their galaxy_score becomes the community_score
                   directly rather than reporting null; (2) BLEND - if we
                   also have our own posts, galaxy_score is folded in as a
                   fifth weighted component alongside the metrics below.
                   LunarCrush tracks established/socially-relevant coins
                   (4,000+), so brand-new meme coins mostly won't match yet
                   - a miss means "not on LunarCrush's radar," not "no
                   community." Community.data_source records which case
                   applied ("posts" | "lunarcrush" | "posts+lunarcrush").
  - Growth:       post-volume change between two equal-length lookback
                   windows (default 7 days each). Not follower growth (see
                   below) - post volume, because that's what we can compute
                   from already-collected data.
  - Engagement:    sum/average of each post's engagement_score (source-
                   specific: Reddit = score + comments*2, X = likes/
                   retweets/etc, CryptoPanic = vote counts).
  - Followers:     ONLY available for Reddit, via the subreddit's subscriber
                   count (a real API call to r/{subreddit}/about). X
                   follower counts aren't fetched - would need a per-author
                   user-lookup call for every unique poster, which is a lot
                   of extra API spend for a proxy signal.
  - Unique posters: distinct author count in the recent window.
  - Organic discussion: unique_posters / total_posts - a community where
                   many different people are posting scores higher than
                   one where a handful of accounts post repeatedly.
  - Spam detection: near-duplicate text detection using word-shingle
                   Jaccard similarity (not just exact-match), so templated
                   spam with minor variations (emoji, punctuation, a swapped
                   word) is now caught too. Still a heuristic, not a real
                   spam classifier - it catches copy-paste-with-edits
                   patterns, not spam that's actually distinct per post
                   (e.g. bot-generated but non-templated text).

If a coin has zero posts in the lookback window, community_score stays
null - there's nothing to measure, so nothing is guessed.
"""

import logging
import math
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.collectors.lunarcrush import LunarCrushCollector
from app.collectors.reddit import RedditCollector
from app.config import settings
from app.models.coin import Coin
from app.models.community import Community
from app.models.score import Score
from app.models.social_post import SocialPost

logger = logging.getLogger(__name__)

ENGAGEMENT_SATURATION = 50.0
FOLLOWERS_SATURATION = 50_000
DUPLICATE_PENALTY_MAX = 25.0
NEAR_DUPLICATE_JACCARD_THRESHOLD = 0.7
NEAR_DUPLICATE_SHINGLE_SIZE = 3  # word n-gram size
# Bounds the O(n^2) near-duplicate comparison cost for very active coins.
NEAR_DUPLICATE_MAX_POSTS_COMPARED = 300


class CommunityIntelligenceService:
    def __init__(self, db: Session):
        self.db = db
        self.reddit = RedditCollector()
        self.lunarcrush = LunarCrushCollector()

    def check_all_active(self) -> dict:
        coins = self.db.query(Coin).filter(Coin.is_active.is_(True)).all()
        analyzed = 0
        no_data = 0
        lunarcrush_metrics = self.lunarcrush.get_metrics_by_symbol()  # one bulk fetch, reused for every coin
        for coin in coins:
            coin_id_for_logging = coin.id
            try:
                result = self.analyze_coin(coin, lunarcrush_metrics)
                self.db.commit()  # commit per-coin so one later failure can't roll back earlier successes
                if result is None:
                    no_data += 1
                else:
                    analyzed += 1
            except Exception:  # noqa: BLE001 - one bad coin shouldn't kill the run
                self.db.rollback()
                logger.exception("Community analysis failed for coin id=%s", coin_id_for_logging)
        return {
            "analyzed": analyzed,
            "no_data": no_data,
            "total_active": len(coins),
            "lunarcrush_coins_tracked": len(lunarcrush_metrics),
            "ran_at": datetime.utcnow().isoformat(),
        }

    def analyze_coin(self, coin: Coin, lunarcrush_metrics: dict | None = None) -> Community | None:
        lunarcrush_metrics = lunarcrush_metrics or {}
        lunarcrush_match = lunarcrush_metrics.get((coin.symbol or "").upper())
        lunarcrush_galaxy_score = lunarcrush_match["galaxy_score"] if lunarcrush_match else None

        lookback = timedelta(days=settings.community_lookback_days)
        now = datetime.utcnow()
        recent_start = now - lookback
        prior_start = now - (lookback * 2)

        timestamp_expr = func.coalesce(SocialPost.posted_at, SocialPost.collected_at)

        recent_posts = (
            self.db.query(SocialPost)
            .filter(SocialPost.coin_id == coin.id, timestamp_expr >= recent_start)
            .all()
        )

        if not recent_posts and lunarcrush_galaxy_score is None:
            # Genuinely nothing to compute from either source.
            self._set_community_score(coin, None)
            return None

        if not recent_posts:
            # Fallback path: our own scanning found nothing, but LunarCrush
            # already tracks this coin (it's crossed into mainstream social
            # visibility) - use their galaxy_score directly rather than
            # reporting null when we actually have a real signal available.
            community = self.db.query(Community).filter(Community.coin_id == coin.id).first()
            if community is None:
                community = Community(coin_id=coin.id)
                self.db.add(community)
            community.lookback_days = settings.community_lookback_days
            community.total_posts = 0
            community.unique_posters = 0
            community.engagement_total = 0.0
            community.avg_engagement_per_post = None
            community.growth_rate_pct = None
            community.organic_discussion_ratio = None
            community.duplicate_content_ratio = None
            community.reddit_subscribers = None
            community.lunarcrush_galaxy_score = lunarcrush_galaxy_score
            community.data_source = "lunarcrush"
            community.community_score = round(_clip(lunarcrush_galaxy_score, 0, 100), 1)
            self._set_community_score(coin, community.community_score)
            self.db.flush()
            return community

        prior_count = (
            self.db.query(func.count(SocialPost.id))
            .filter(
                SocialPost.coin_id == coin.id,
                timestamp_expr >= prior_start,
                timestamp_expr < recent_start,
            )
            .scalar()
        )

        metrics = self._compute_metrics(recent_posts, prior_count)
        reddit_subscribers = self._lookup_reddit_subscribers(recent_posts)

        community = self.db.query(Community).filter(Community.coin_id == coin.id).first()
        if community is None:
            community = Community(coin_id=coin.id)
            self.db.add(community)

        community.lookback_days = settings.community_lookback_days
        community.total_posts = metrics["total_posts"]
        community.unique_posters = metrics["unique_posters"]
        community.engagement_total = metrics["engagement_total"]
        community.avg_engagement_per_post = metrics["avg_engagement_per_post"]
        community.growth_rate_pct = metrics["growth_rate_pct"]
        community.organic_discussion_ratio = metrics["organic_discussion_ratio"]
        community.duplicate_content_ratio = metrics["duplicate_content_ratio"]
        community.reddit_subscribers = reddit_subscribers
        community.lunarcrush_galaxy_score = lunarcrush_galaxy_score
        community.data_source = "posts+lunarcrush" if lunarcrush_galaxy_score is not None else "posts"

        community_score = self._community_score(metrics, reddit_subscribers, lunarcrush_galaxy_score)
        community.community_score = community_score

        self._set_community_score(coin, community_score)
        self.db.flush()
        return community

    def _compute_metrics(self, posts: list[SocialPost], prior_count: int) -> dict:
        total_posts = len(posts)
        authors = [p.author for p in posts if p.author]
        unique_posters = len(set(authors))
        engagement_total = sum(p.engagement_score or 0.0 for p in posts)
        avg_engagement = engagement_total / total_posts if total_posts else None

        growth_rate_pct = None
        if prior_count and prior_count > 0:
            growth_rate_pct = ((total_posts - prior_count) / prior_count) * 100

        organic_ratio = (unique_posters / total_posts) if total_posts else None

        normalized_texts = [_normalize_text(p.text) for p in posts if p.text]
        duplicate_ratio = self._near_duplicate_ratio(normalized_texts)

        return {
            "total_posts": total_posts,
            "unique_posters": unique_posters,
            "engagement_total": engagement_total,
            "avg_engagement_per_post": avg_engagement,
            "growth_rate_pct": growth_rate_pct,
            "organic_discussion_ratio": organic_ratio,
            "duplicate_content_ratio": duplicate_ratio,
        }

    def _near_duplicate_ratio(self, texts: list[str]) -> float:
        """Fraction of posts that are a near-duplicate (Jaccard similarity
        >= NEAR_DUPLICATE_JACCARD_THRESHOLD on word shingles) of an earlier
        post in the window. Greedy: once a post is marked a duplicate of
        something, it's not also compared as a potential "original" against
        later posts - this slightly undercounts in pathological cases but
        keeps the algorithm simple and O(n^2) bounded rather than needing
        clustering. Capped at NEAR_DUPLICATE_MAX_POSTS_COMPARED for very
        active coins, since this is O(n^2) in shingle-set comparisons."""
        if not texts:
            return 0.0

        sample = texts[:NEAR_DUPLICATE_MAX_POSTS_COMPARED]
        shingle_sets = [_shingles(t) for t in sample]
        is_duplicate = [False] * len(sample)

        for i in range(len(sample)):
            if is_duplicate[i]:
                continue
            for j in range(i + 1, len(sample)):
                if is_duplicate[j]:
                    continue
                if _jaccard(shingle_sets[i], shingle_sets[j]) >= NEAR_DUPLICATE_JACCARD_THRESHOLD:
                    is_duplicate[j] = True

        return sum(is_duplicate) / len(sample)

    def _lookup_reddit_subscribers(self, posts: list[SocialPost]) -> int | None:
        if not self.reddit.is_configured():
            return None
        subreddits = [p.community for p in posts if p.community]
        if not subreddits:
            return None
        top_subreddit = Counter(subreddits).most_common(1)[0][0]
        info = self.reddit.get_subreddit_about(top_subreddit)
        return info.get("subscribers") if info else None

    def _community_score(
        self, metrics: dict, reddit_subscribers: int | None, lunarcrush_galaxy_score: float | None = None
    ) -> float:
        components: dict[str, float] = {}
        weights = {"engagement": 0.30, "organic": 0.25, "growth": 0.15, "followers": 0.10, "lunarcrush": 0.20}

        avg_eng = metrics["avg_engagement_per_post"]
        if avg_eng is not None:
            components["engagement"] = _clip(
                100 * math.log10(1 + max(avg_eng, 0)) / math.log10(1 + ENGAGEMENT_SATURATION), 0, 100
            )

        if metrics["organic_discussion_ratio"] is not None:
            components["organic"] = _clip(metrics["organic_discussion_ratio"] * 100, 0, 100)

        if metrics["growth_rate_pct"] is not None:
            components["growth"] = _clip((metrics["growth_rate_pct"] + 100) / 4, 0, 100)

        if reddit_subscribers is not None:
            components["followers"] = _clip(
                100 * math.log10(1 + reddit_subscribers) / math.log10(1 + FOLLOWERS_SATURATION), 0, 100
            )

        if lunarcrush_galaxy_score is not None:
            # Galaxy Score is already a 0-100 scale per LunarCrush's own
            # product - used directly, no transformation needed.
            components["lunarcrush"] = _clip(lunarcrush_galaxy_score, 0, 100)

        if not components:
            return 0.0

        total_weight = sum(weights[k] for k in components)
        weighted_avg = sum(components[k] * weights[k] for k in components) / total_weight

        spam_penalty = metrics["duplicate_content_ratio"] * DUPLICATE_PENALTY_MAX
        return round(_clip(weighted_avg - spam_penalty, 0, 100), 1)

    def _set_community_score(self, coin: Coin, community_score: float | None) -> None:
        score = self.db.query(Score).filter(Score.coin_id == coin.id).first()
        if score is None:
            score = Score(coin_id=coin.id)
            self.db.add(score)
        score.community_score = community_score
        self.db.flush()


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def _shingles(text: str, n: int = NEAR_DUPLICATE_SHINGLE_SIZE) -> set:
    words = text.split()
    if len(words) < n:
        return {text} if text else set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    union = len(a | b)
    return (len(a & b) / union) if union else 0.0


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
