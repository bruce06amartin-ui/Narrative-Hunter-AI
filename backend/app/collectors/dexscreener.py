"""
DexScreener collector (MODULE 1: Coin Discovery Service - enrichment).

Docs: https://docs.dexscreener.com/api/reference
Endpoint used: GET /latest/dex/pairs/{chainId}/{pairId}
No API key required (public, rate limited ~300 req/min).

DexScreener doesn't expose a clean "newest pairs" feed on the free tier,
so it's used here to *enrich/cross-check* pools that GeckoTerminal already
discovered, rather than as a primary discovery source. This also gives a
second reading on liquidity/volume, which is useful input for rug-risk
checks in a later module.
"""

import logging

from app.collectors.base import BaseCollector, get_json, CollectorHTTPError

logger = logging.getLogger(__name__)

BASE_URL = "https://api.dexscreener.com/latest/dex"

# DexScreener chainId slugs
CHAIN_SLUG_MAP = {
    "solana": "solana",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "base": "base",
}


class DexScreenerCollector(BaseCollector):
    name = "dexscreener"

    def discover(self) -> list[dict]:
        # Not used as a primary discovery source - see module docstring.
        raise NotImplementedError(
            "DexScreenerCollector is enrichment-only in this MVP. "
            "Use enrich_pair() for a specific chain/pair_address."
        )

    def enrich_pair(self, chain: str, pair_address: str) -> dict | None:
        """Fetch a single pair's current stats from DexScreener.
        Returns None if the pair can't be found (e.g. too new, or already
        delisted) rather than raising, so callers can just skip enrichment."""
        chain_slug = CHAIN_SLUG_MAP.get(chain.lower(), chain.lower())
        url = f"{BASE_URL}/pairs/{chain_slug}/{pair_address}"

        try:
            payload = get_json(url)
        except CollectorHTTPError as e:
            logger.info("DexScreener enrichment miss for %s/%s: %s", chain, pair_address, e)
            return None

        pairs = payload.get("pairs") or []
        if not pairs:
            return None

        pair = pairs[0]
        return {
            "liquidity_usd": _safe_get(pair, "liquidity", "usd"),
            "volume_24h_usd": _safe_get(pair, "volume", "h24"),
            "price_usd": _to_float(pair.get("priceUsd")),
            "price_change_1h": _safe_get(pair, "priceChange", "h1"),
            "price_change_24h": _safe_get(pair, "priceChange", "h24"),
            "fdv_usd": _to_float(pair.get("fdv")),
            "market_cap_usd": _to_float(pair.get("marketCap")),
        }


def _safe_get(d: dict, *keys):
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return _to_float(d)


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
