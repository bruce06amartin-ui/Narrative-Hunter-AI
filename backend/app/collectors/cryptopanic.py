"""
CryptoPanic collector (MODULE 2: Narrative Scanner - crypto news source).

Docs: https://cryptopanic.com/developers/api/

CryptoPanic's free "Developer" API plan was discontinued April 1, 2026 -
current access requires a paid plan token. This collector is written
against their documented request/response shape and is gated behind an
optional CRYPTOPANIC_API_TOKEN; if unset, it's skipped rather than faking
news data. If you have a token (free trial or paid), it should work as-is.
"""

import logging

from app.collectors.base import get_json, CollectorHTTPError
from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://cryptopanic.com/api/v1/posts/"


class CryptoPanicCollector:
    name = "cryptopanic"

    def is_configured(self) -> bool:
        return bool(settings.cryptopanic_api_token)

    def get_posts(self, currency_code: str, limit: int = 25) -> list[dict]:
        if not self.is_configured() or not currency_code:
            return []

        params = {
            "auth_token": settings.cryptopanic_api_token,
            "currencies": currency_code.upper(),
            "public": "true",
        }

        try:
            payload = get_json(BASE_URL, params=params)
        except CollectorHTTPError as e:
            logger.warning("CryptoPanic request failed for %s: %s", currency_code, e)
            return []

        posts = []
        for row in (payload.get("results") or [])[:limit]:
            try:
                posts.append(self._normalize(row))
            except Exception as e:  # noqa: BLE001
                logger.warning("Skipping malformed CryptoPanic post: %s", e)
        return posts

    def _normalize(self, row: dict) -> dict:
        votes = row.get("votes", {}) or {}
        engagement = sum(float(v) for v in votes.values() if isinstance(v, (int, float)))
        return {
            "external_id": str(row.get("id")),
            "author": row.get("source", {}).get("title") if isinstance(row.get("source"), dict) else None,
            "text": row.get("title", ""),
            "url": row.get("url"),
            "engagement_score": engagement,
            "posted_at_iso": row.get("published_at"),
        }
