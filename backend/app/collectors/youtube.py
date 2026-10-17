"""
YouTube Data API v3 collector (MODULE 2 extension: narrative scanning).

Docs verified: https://developers.google.com/youtube/v3/docs/search/list
and https://developers.google.com/youtube/v3/docs/videos/list

Genuinely free tier, confirmed via multiple independent sources: 10,000
quota units/day per Google Cloud project, no credit card required. The
catch: search.list costs 100 units per call, so the free tier allows
roughly 100 searches/day - a real, tight budget, same "design carefully
around it" discipline as every other free-tier integration built
tonight. videos.list (used here to fetch view counts) costs only 1 unit
and can batch up to 50 video IDs per call, so it's used to cheaply enrich
whatever search already found rather than being a second search cost.

Auth: query param "key": YOUTUBE_API_KEY (no special header needed).
"""

import logging

from app.collectors.base import get_json, CollectorHTTPError
from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://www.googleapis.com/youtube/v3"


class YouTubeCollector:
    name = "youtube"

    def is_configured(self) -> bool:
        return bool(settings.youtube_api_key)

    def search_recent_videos(self, query: str, published_after_iso: str, max_results: int = 5) -> list[dict]:
        """One search.list call - costs 100 quota units. Returns up to
        max_results recent videos matching the query, newest first."""
        if not self.is_configured():
            return []
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "date",
            "publishedAfter": published_after_iso,
            "maxResults": max_results,
            "key": settings.youtube_api_key,
        }
        try:
            payload = get_json(f"{BASE_URL}/search", params=params)
        except CollectorHTTPError as e:
            logger.info("YouTube search miss for query=%r: %s", query, e)
            return []

        items = payload.get("items") or []
        if not isinstance(items, list):
            logger.warning("Unexpected YouTube search response shape for query=%r", query)
            return []

        results = []
        for item in items:
            try:
                video_id = (item.get("id") or {}).get("videoId")
                snippet = item.get("snippet") or {}
                if not video_id:
                    continue
                results.append({
                    "video_id": video_id,
                    "title": snippet.get("title"),
                    "description": snippet.get("description"),
                    "channel_title": snippet.get("channelTitle"),
                    "published_at": snippet.get("publishedAt"),
                })
            except Exception as e:  # noqa: BLE001
                logger.warning("Skipping malformed YouTube search result for query=%r: %s", query, e)
        return results

    def get_view_counts(self, video_ids: list[str]) -> dict[str, int]:
        """One videos.list call per up to 50 IDs - costs only 1 unit each,
        regardless of how many IDs are batched in. Returns {video_id: view_count},
        omitting any ID that failed to parse rather than failing the whole batch."""
        if not self.is_configured() or not video_ids:
            return {}
        counts: dict[str, int] = {}
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]
            params = {"part": "statistics", "id": ",".join(batch), "key": settings.youtube_api_key}
            try:
                payload = get_json(f"{BASE_URL}/videos", params=params)
            except CollectorHTTPError as e:
                logger.info("YouTube view-count batch fetch failed: %s", e)
                continue
            for item in payload.get("items") or []:
                try:
                    vid = item.get("id")
                    view_count = (item.get("statistics") or {}).get("viewCount")
                    if vid and view_count is not None:
                        counts[vid] = int(view_count)
                except (TypeError, ValueError) as e:
                    logger.warning("Skipping malformed YouTube stats entry: %s", e)
        return counts
