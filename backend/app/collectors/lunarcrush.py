"""
LunarCrush collector (MODULE 4: Community Intelligence - free bonus source).

Docs verified against: https://github.com/lunarcrush/api (official v4 docs repo)
Endpoint: GET https://lunarcrush.com/api4/public/coins/list/v1
Auth: Authorization: Bearer {LUNARCRUSH_API_KEY} (free tier: 4 requests/minute)

WHY THIS IS A BULK ENDPOINT, NOT A PER-COIN LOOKUP: coins/list/v1 returns a
snapshot of LunarCrush's ENTIRE tracked coin universe (galaxy_score, alt_rank,
social_volume, social_dominance, etc.) in one response - up to 1000 results
per page. This means checking 1 of our coins costs the same as checking all
of them: one fetch, then a local dict lookup by symbol. The 4 req/min limit
therefore isn't a "which coins do we afford to check" problem - it's a "how
many pages do we pull, how often" problem. LunarCrush's own docs state this
endpoint is "heavily cached and up to 1 hour behind" on their end, so
refetching faster than hourly is pointless regardless of rate limit - our
own cache TTL matches that.

COVERAGE REALITY: LunarCrush tracks "4,000+ cryptocurrencies" - i.e.
established, socially-relevant coins. Brand-new meme coins (minutes/hours
old) will mostly NOT be in this list yet. Treat a symbol match here as a
meaningful positive signal (this coin has crossed into mainstream social
tracking), and a non-match as "not yet visible to LunarCrush," not as
evidence the coin has no community at all.

Field names verified via two independent real usage examples (a REST fetch
example and a GraphQL wrapper mirroring the same underlying fields) that
agreed on: symbol, name, price, percent_change_24h, social_volume,
social_dominance, galaxy_score, alt_rank. Not verified against a live
response in this build environment (no outbound network access here) -
parsing is defensive, so a renamed/missing field degrades gracefully rather
than crashing the whole fetch.
"""

import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://lunarcrush.com/api4/public"
_CACHE_TTL_SECONDS = 3600  # matches LunarCrush's own ~1h refresh cadence for this endpoint
_MAX_PAGES = 4  # 4 pages x 1000 = up to 4,000 coins, matching their stated universe size
_PAGE_SIZE = 1000
_MIN_SECONDS_BETWEEN_REQUESTS = 15.0  # free tier: 4 requests/minute = 1 every 15s

_cache: dict = {"by_symbol": None, "fetched_at": 0.0}


class LunarCrushCollector:
    name = "lunarcrush"

    def is_configured(self) -> bool:
        return bool(settings.lunarcrush_api_key)

    def get_metrics_by_symbol(self) -> dict:
        """Returns {SYMBOL: {galaxy_score, alt_rank, social_volume,
        social_dominance, percent_change_24h}, ...} for every coin
        LunarCrush currently tracks, refetching at most once per
        _CACHE_TTL_SECONDS. Call this ONCE per cycle and reuse the result
        for every coin you're checking - never call per-coin."""
        if not self.is_configured():
            return {}

        now = time.time()
        if _cache["by_symbol"] is not None and (now - _cache["fetched_at"]) < _CACHE_TTL_SECONDS:
            return _cache["by_symbol"]

        by_symbol: dict = {}
        try:
            with httpx.Client(timeout=15.0) as client:
                for page in range(_MAX_PAGES):
                    if page > 0:
                        time.sleep(_MIN_SECONDS_BETWEEN_REQUESTS)  # respect 4 req/min even within one fetch

                    resp = client.get(
                        f"{BASE_URL}/coins/list/v1",
                        params={"limit": _PAGE_SIZE, "page": page, "sort": "galaxy_score", "desc": "true"},
                        headers={"Authorization": f"Bearer {settings.lunarcrush_api_key}"},
                    )
                    if resp.status_code >= 400:
                        logger.warning("LunarCrush fetch failed (page %d): %s %s", page, resp.status_code, resp.text[:300])
                        break

                    rows = (resp.json() or {}).get("data", [])
                    if not rows:
                        break  # ran out of pages before hitting _MAX_PAGES

                    for row in rows:
                        symbol = (row.get("symbol") or "").upper()
                        if not symbol:
                            continue
                        by_symbol[symbol] = {
                            "galaxy_score": _to_float(row.get("galaxy_score")),
                            "alt_rank": _to_float(row.get("alt_rank")),
                            "social_volume": _to_float(row.get("social_volume") or row.get("social_volume_24h")),
                            "social_dominance": _to_float(row.get("social_dominance")),
                            "percent_change_24h": _to_float(row.get("percent_change_24h")),
                        }

                    if len(rows) < _PAGE_SIZE:
                        break  # last page was partial - nothing more to fetch
        except httpx.HTTPError as e:
            logger.warning("LunarCrush fetch errored: %s", e)
            return _cache["by_symbol"] or {}

        if by_symbol:
            _cache["by_symbol"] = by_symbol
            _cache["fetched_at"] = now
            logger.info("LunarCrush snapshot refreshed: %d coins tracked", len(by_symbol))
        return _cache["by_symbol"] or {}


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
