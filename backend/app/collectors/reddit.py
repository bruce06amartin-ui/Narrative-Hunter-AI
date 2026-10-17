"""
Reddit collector (MODULE 2: Narrative Scanner).

Docs: https://www.reddit.com/dev/api (official Data API, OAuth2 required)

IMPORTANT 2026 CONTEXT: Reddit shut down unauthenticated .json access in
May 2026 and closed self-service OAuth app creation in November 2025 under
its "Responsible Builder Policy." New API credentials now require a manual
application/review through Reddit's developer support form - they are not
something you can just generate in a dashboard anymore. If you already
have OAuth app credentials from before the policy change, they still work
here. If not, this collector will simply be skipped (see is_configured())
rather than the platform pretending Reddit data is being collected.

Uses the standard OAuth2 client-credentials grant (app-only auth, no user
context needed for public read-only search):
  1. POST https://www.reddit.com/api/v1/access_token (Basic auth: client_id:secret)
  2. GET https://oauth.reddit.com/search with the returned bearer token
"""

import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
SEARCH_URL = "https://oauth.reddit.com/search"

_token_cache = {"access_token": None, "expires_at": 0}


class RedditCollector:
    name = "reddit"

    def is_configured(self) -> bool:
        return bool(settings.reddit_client_id and settings.reddit_client_secret)

    def search(self, query: str, limit: int = 25) -> list[dict]:
        if not self.is_configured():
            return []

        token = self._get_access_token()
        if not token:
            return []

        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": settings.reddit_user_agent,
        }
        params = {"q": query, "sort": "new", "limit": limit, "type": "link"}

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(SEARCH_URL, params=params, headers=headers)
                if resp.status_code >= 400:
                    logger.warning("Reddit search failed: %s %s", resp.status_code, resp.text[:300])
                    return []
                payload = resp.json()
        except httpx.HTTPError as e:
            logger.warning("Reddit search request failed: %s", e)
            return []

        posts = []
        for child in payload.get("data", {}).get("children", []):
            try:
                posts.append(self._normalize(child.get("data", {})))
            except Exception as e:  # noqa: BLE001
                logger.warning("Skipping malformed Reddit post: %s", e)
        return posts

    def _normalize(self, post: dict) -> dict:
        return {
            "external_id": post["id"],
            "author": post.get("author"),
            "text": (post.get("title") or "") + ("\n" + post["selftext"] if post.get("selftext") else ""),
            "url": f"https://reddit.com{post.get('permalink', '')}",
            "engagement_score": float(post.get("score", 0)) + float(post.get("num_comments", 0)) * 2,
            "posted_at_epoch": post.get("created_utc"),
            "subreddit": post.get("subreddit"),
        }

    def get_subreddit_about(self, subreddit: str) -> dict | None:
        """MODULE 4 (Community Intelligence) 'Followers' proxy: subscriber
        count for a subreddit. Returns None if unconfigured or the call fails."""
        if not self.is_configured():
            return None

        token = self._get_access_token()
        if not token:
            return None

        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": settings.reddit_user_agent,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(f"https://oauth.reddit.com/r/{subreddit}/about", headers=headers)
                if resp.status_code >= 400:
                    return None
                data = resp.json().get("data", {})
        except httpx.HTTPError:
            return None

        return {
            "subscribers": data.get("subscribers"),
            "active_user_count": data.get("active_user_count"),
        }

    def _get_access_token(self) -> str | None:
        if _token_cache["access_token"] and _token_cache["expires_at"] > time.time() + 30:
            return _token_cache["access_token"]

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    TOKEN_URL,
                    data={"grant_type": "client_credentials"},
                    auth=(settings.reddit_client_id, settings.reddit_client_secret),
                    headers={"User-Agent": settings.reddit_user_agent},
                )
                if resp.status_code >= 400:
                    logger.warning("Reddit OAuth token request failed: %s %s", resp.status_code, resp.text[:300])
                    return None
                data = resp.json()
        except httpx.HTTPError as e:
            logger.warning("Reddit OAuth token request errored: %s", e)
            return None

        _token_cache["access_token"] = data.get("access_token")
        _token_cache["expires_at"] = time.time() + data.get("expires_in", 3600)
        return _token_cache["access_token"]
