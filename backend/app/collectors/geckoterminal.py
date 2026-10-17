"""
GeckoTerminal collector (MODULE 1: Coin Discovery Service).

Docs: https://www.geckoterminal.com/dex-api
Endpoint used: GET /api/v2/networks/{network}/new_pools
No API key required for the public tier (rate limited ~30 req/min).

This is the primary discovery source because it directly exposes a
"newest pools" feed per network, which maps cleanly onto "newly launched
token" from the spec. DexScreener (see dexscreener.py) is used for
enrichment/cross-checking instead, since its public search API isn't a
clean "newest" feed.
"""

import logging
import time
from datetime import datetime, timezone

from app.collectors.base import BaseCollector, get_json, CollectorHTTPError

logger = logging.getLogger(__name__)

BASE_URL = "https://api.geckoterminal.com/api/v2"

# Matches the shared per-request throttle in collectors/base.py
# (_MIN_INTERVAL_SECONDS["api.geckoterminal.com"]) - kept as an explicit
# local constant rather than importing that private dict, so this pacing
# stays correct even if the shared value changes for unrelated reasons.
SINGLE_REQUEST_INTERVAL_SECONDS = 2.2

# GeckoTerminal network slugs differ slightly from common chain names.
NETWORK_SLUG_MAP = {
    "solana": "solana",
    "eth": "eth",
    "ethereum": "eth",
    "base": "base",
}


class GeckoTerminalCollector(BaseCollector):
    name = "geckoterminal"

    def __init__(self, networks: list[str]):
        self.networks = [NETWORK_SLUG_MAP.get(n.lower(), n.lower()) for n in networks]

    def discover(self) -> list[dict]:
        results: list[dict] = []
        for network in self.networks:
            try:
                results.extend(self._discover_network(network))
            except CollectorHTTPError as e:
                logger.warning("GeckoTerminal discovery failed for network=%s: %s", network, e)
            except Exception as e:  # noqa: BLE001 - one bad network shouldn't kill the cycle
                logger.exception("Unexpected GeckoTerminal error for network=%s: %s", network, e)
        return results

    def _discover_network(self, network: str) -> list[dict]:
        url = f"{BASE_URL}/networks/{network}/new_pools"
        payload = get_json(url, params={"include": "base_token,quote_token"})

        # Build a lookup of included token resources so we can pull the
        # underlying contract address (new_pools only gives pool address
        # + a relationship id by default).
        included_tokens = {
            item["id"]: item
            for item in payload.get("included", [])
            if item.get("type") == "token"
        }

        normalized = []
        for pool in payload.get("data", []):
            try:
                normalized.append(self._normalize_pool(network, pool, included_tokens))
            except Exception as e:  # noqa: BLE001
                logger.warning("Skipping malformed GeckoTerminal pool record: %s", e)
        return normalized

    def _normalize_pool(self, network: str, pool: dict, included_tokens: dict) -> dict:
        attrs = pool.get("attributes", {})
        rel = pool.get("relationships", {})

        base_token_ref = rel.get("base_token", {}).get("data", {})
        base_token = included_tokens.get(base_token_ref.get("id"), {})
        base_token_attrs = base_token.get("attributes", {})

        contract_address = base_token_attrs.get("address")
        pool_address = attrs.get("address")

        launch_time = None
        if attrs.get("pool_created_at"):
            launch_time = datetime.fromisoformat(attrs["pool_created_at"].replace("Z", "+00:00"))

        volume_24h = None
        if isinstance(attrs.get("volume_usd"), dict):
            volume_24h = _to_float(attrs["volume_usd"].get("h24"))

        price_change_1h = None
        price_change_24h = None
        if isinstance(attrs.get("price_change_percentage"), dict):
            price_change_1h = _to_float(attrs["price_change_percentage"].get("h1"))
            price_change_24h = _to_float(attrs["price_change_percentage"].get("h24"))

        return {
            "contract_address": contract_address,
            "pair_address": pool_address,
            "chain": network,
            "source": self.name,
            "symbol": base_token_attrs.get("symbol"),
            "name": base_token_attrs.get("name") or attrs.get("name"),
            "launch_time": launch_time or datetime.now(timezone.utc),
            "liquidity_usd": _to_float(attrs.get("reserve_in_usd")),
            "market_cap_usd": _to_float(attrs.get("market_cap_usd")),
            "fdv_usd": _to_float(attrs.get("fdv_usd")),
            "volume_24h_usd": volume_24h,
            "price_usd": _to_float(attrs.get("base_token_price_usd")),
            "price_change_1h": price_change_1h,
            "price_change_24h": price_change_24h,
        }


    def refresh_prices(self, network: str, pool_addresses: list[str]) -> list[dict]:
        """Batch-refresh CURRENT price/liquidity/volume for KNOWN pools, up
        to 30 addresses per call. This is what keeps price_history
        accumulating for a coin after it ages out of the new_pools feed -
        without this, discover() above is the ONLY way this system ever
        gets a fresh price reading, and it naturally stops returning a
        coin once it's no longer "new." Without a refresh mechanism,
        MODULE 6 (trend detection) can never mature past whatever data was
        captured in a coin's first hour or so of existence - confirmed via
        real production data (coins 20+ hours old still showing zero
        trend signal).
        Docs: GET /networks/{network}/pools/multi/{addresses}
        (apiguide.geckoterminal.com/changelogs - added alongside the
        equivalent /tokens/multi/{addresses} endpoint). Same Pool resource
        schema as new_pools, so _normalize_pool is reused directly rather
        than duplicated.

        RATE LIMITING: confirmed via real production logs that the shared
        per-request host throttle in collectors/base.py (~2.2s/request,
        tuned for single-address calls like new_pools) is NOT sufficient
        for this endpoint - repeated 429s occurred even with that spacing
        respected. GeckoTerminal almost certainly meters usage per-address
        requested here, not per HTTP call, so a 30-address batch costs
        roughly 30x what a single-address request costs against the same
        budget. This method adds its own address-count-proportional wait
        on top of the shared throttle to account for that - not a guess,
        a direct response to observed 429s at the previous pacing."""
        if not pool_addresses:
            return []
        batch = pool_addresses[:30]  # API caps at 30/call

        # Address-count-proportional pacing: treat each address in this
        # batch as costing the same as one single-address request would
        # under the shared host throttle (SINGLE_REQUEST_INTERVAL_SECONDS).
        # This is IN ADDITION to (not instead of) the shared per-request
        # throttle already applied inside get_json().
        wait_seconds = max(0.0, (len(batch) - 1) * SINGLE_REQUEST_INTERVAL_SECONDS)
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        addresses_param = ",".join(batch)
        url = f"{BASE_URL}/networks/{network}/pools/multi/{addresses_param}"
        try:
            payload = get_json(url, params={"include": "base_token,quote_token"})
        except CollectorHTTPError as e:
            logger.info("GeckoTerminal price refresh miss for network=%s: %s", network, e)
            return []

        included_tokens = {
            item["id"]: item
            for item in payload.get("included", [])
            if item.get("type") == "token"
        }
        results = []
        for pool in payload.get("data", []):
            try:
                results.append(self._normalize_pool(network, pool, included_tokens))
            except Exception as e:  # noqa: BLE001
                logger.warning("Skipping malformed GeckoTerminal pool record during refresh: %s", e)
        return results

    def get_token_info(self, network: str, token_address: str) -> dict | None:
        """Fetch a token's social links (telegram_handle, twitter_handle,
        websites). Real, documented, keyless endpoint:
        GET /networks/{network}/tokens/{address}/info
        (see https://apiguide.geckoterminal.com/changelogs). This is what
        makes a real Telegram collector possible - it tells us which public
        channel actually belongs to a given coin, which is the piece that
        was missing before. Returns None on any failure - social links are
        a nice-to-have enrichment, not required for discovery to succeed."""
        network_slug = NETWORK_SLUG_MAP.get(network.lower(), network.lower())
        url = f"{BASE_URL}/networks/{network_slug}/tokens/{token_address}/info"

        try:
            payload = get_json(url)
        except CollectorHTTPError as e:
            logger.info("GeckoTerminal token info miss for %s/%s: %s", network, token_address, e)
            return None

        attrs = (payload.get("data") or {}).get("attributes", {})
        return {
            "telegram_handle": attrs.get("telegram_handle"),
            "twitter_handle": attrs.get("twitter_handle"),
            "websites": attrs.get("websites") or [],
        }


    def get_all_pools_for_token(self, network: str, token_address: str) -> list[dict]:
        """Find every pool currently trading a given token contract.
        Confirmed via GeckoTerminal's own FAQ docs (apiguide.geckoterminal.com/faq):
        GET /networks/{network}/tokens/{address}/pools, returns up to 20
        pools ranked by GeckoTerminal's own liquidity/volume ranking.
        This is what makes pool-migration detection possible: a coin
        first discovered on a thin, low-liquidity pool (e.g. a pump.fun
        bonding-curve-adjacent pool) can later have its REAL trading
        move to a different, much healthier pool for the same
        underlying token - something the original discovery/refresh
        flow would never notice on its own, since both only ever look
        at the ONE pool address a coin was first found on."""
        network_slug = NETWORK_SLUG_MAP.get(network.lower(), network.lower())
        url = f"{BASE_URL}/networks/{network_slug}/tokens/{token_address}/pools"
        try:
            payload = get_json(url, params={"include": "base_token,quote_token"})
        except CollectorHTTPError as e:
            logger.info("GeckoTerminal all-pools miss for %s/%s: %s", network, token_address, e)
            return []

        included_tokens = {
            item["id"]: item
            for item in payload.get("included", [])
            if item.get("type") == "token"
        }
        results = []
        for pool in payload.get("data", []):
            try:
                results.append(self._normalize_pool(network_slug, pool, included_tokens))
            except Exception as e:  # noqa: BLE001
                logger.warning("Skipping malformed GeckoTerminal pool record in all-pools response: %s", e)
        return results


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
