"""
X/Twitter collector (MODULE 2: Narrative Scanner - X posts).

Docs: https://docs.x.com/x-api/introduction
Endpoint: GET https://api.x.com/2/tweets/search/recent

IMPORTANT 2026 CONTEXT: X moved to pay-per-use pricing in February 2026 -
there is no free tier for new developers (existing free-tier users were
migrated to pay-per-use with a one-time credit voucher). This collector is
written against the current v2 recent-search endpoint and gated behind an
optional TWITTER_BEARER_TOKEN; without one, it's skipped rather than faking
data. Recent search only covers the last 7 days regardless of plan.
"""

import logging

from app.collectors.base import get_json, CollectorHTTPError
from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.x.com/2/tweets/search/recent"


class TwitterCollector:
    name = "twitter"

    def is_configured(self) -> bool:
        return bool(settings.twitter_bearer_token)

    def search(self, query: str, max_results: int = 25) -> list[dict]:
        if not self.is_configured():
            return []

        params = {
            "query": f"({query}) -is:retweet lang:en",
            "max_results": max(10, min(max_results, 100)),
            "tweet.fields": "created_at,public_metrics,author_id",
        }
        headers = {"Authorization": f"Bearer {settings.twitter_bearer_token}"}

        try:
            payload = get_json(BASE_URL, params=params, headers=headers)
        except CollectorHTTPError as e:
            logger.warning("X search failed for query '%s': %s", query, e)
            return []

        posts = []
        for row in payload.get("data", []) or []:
            try:
                posts.append(self._normalize(row))
            except Exception as e:  # noqa: BLE001
                logger.warning("Skipping malformed X post: %s", e)
        return posts

    def _normalize(self, row: dict) -> dict:
        metrics = row.get("public_metrics", {}) or {}
        engagement = (
            metrics.get("like_count", 0)
            + metrics.get("retweet_count", 0) * 2
            + metrics.get("reply_count", 0)
            + metrics.get("quote_count", 0)
        )
        return {
            "external_id": row["id"],
            "author": row.get("author_id"),
            "text": row.get("text", ""),
            "url": f"https://x.com/i/web/status/{row['id']}",
            "engagement_score": float(engagement),
            "posted_at_iso": row.get("created_at"),
        }
