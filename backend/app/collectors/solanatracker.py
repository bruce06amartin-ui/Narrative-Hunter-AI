"""
Solana Tracker collector (MODULE 3 extension: Solana wallet intelligence).

Docs verified against: https://www.solanatracker.io/data-api and
https://docs.solanatracker.io/ (their own published endpoint list).

Base URL: https://data.solanatracker.io
Auth: header "x-api-key": SOLANATRACKER_API_KEY (real free tier, confirmed
via the actual pricing page: 2,500 requests/month, 3 requests/second rate
limit. An earlier version of this file cited 10,000/month based on a
search result that turned out to be wrong - fixed after the real pricing
page was checked directly, same as several other integrations tonight).

Two endpoints used, both confirmed in their own docs:
  GET /tokens/{address}/holders
      Top 100 holders with percentages for a given token mint address.
  GET /v2/pnl/wallets/{wallet}/tokens/{token}
      Realized/unrealized profit-and-loss for a SPECIFIC wallet on a
      SPECIFIC token - this is genuinely MORE precise than the EVM wallet
      module's approach (which uses a nearest-price-history-snapshot proxy
      for ROI, documented as an approximation in wallet_service.py). Here,
      PnL comes directly from the API's own trade reconstruction.

BUDGET REALITY: 2,500 requests/month is real and genuinely tight at
meme-coin scale.
1 holders call + N per-holder PnL calls per coin adds up fast - see
solana_wallet_service.py for how this is bounded to stay predictable
(same "hard ceiling" philosophy as the Anthropic narrative cost cap).

Field names below are based on the vendor's own documented response shape
descriptions (e.g. "top 100 holders with percentages", PnL response
described as profit/loss with position data) - not verified against a live
response in this build environment (no outbound network access here).
Parsing is defensive throughout: a missing/renamed field degrades that one
holder's data, not the whole fetch.
"""

import logging

from app.collectors.base import get_json, CollectorHTTPError
from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://data.solanatracker.io"


class SolanaTrackerCollector:
    name = "solanatracker"

    def is_configured(self) -> bool:
        return bool(settings.solanatracker_api_key)

    def _headers(self) -> dict:
        return {"x-api-key": settings.solanatracker_api_key}

    def get_top_holders(self, token_address: str, limit: int = 10) -> list[dict]:
        """Returns up to `limit` holder wallet addresses with their
        percentage ownership, ranked by size. Capped well below the API's
        own 100-holder max - each holder returned here costs one MORE
        request (the PnL lookup), so this directly controls per-coin
        request cost. See solana_wallet_service.py for the actual cap
        applied in practice."""
        if not self.is_configured():
            return []
        url = f"{BASE_URL}/tokens/{token_address}/holders"
        try:
            payload = get_json(url, headers=self._headers())
        except CollectorHTTPError as e:
            logger.info("Solana Tracker holders fetch miss for %s: %s", token_address, e)
            return []

        raw_holders = payload.get("accounts") or payload.get("holders") or payload.get("data") or []
        if not isinstance(raw_holders, list):
            logger.warning("Unexpected Solana Tracker holders response shape for %s", token_address)
            return []

        results = []
        for h in raw_holders[:limit]:
            try:
                address = h.get("address") or h.get("wallet") or h.get("owner")
                if not address:
                    continue
                pct = h.get("percentage") or h.get("percent") or h.get("pct")
                results.append({"address": address, "percentage": _to_float(pct)})
            except Exception as e:  # noqa: BLE001
                logger.warning("Skipping malformed holder entry for %s: %s", token_address, e)
        return results

    def get_wallet_token_pnl(self, wallet_address: str, token_address: str) -> dict | None:
        """Real profit-and-loss for one wallet on one specific token -
        actual trade-reconstructed data from the API, not a price-proxy
        estimate like the EVM module uses."""
        if not self.is_configured():
            return None
        url = f"{BASE_URL}/v2/pnl/wallets/{wallet_address}/tokens/{token_address}"
        try:
            payload = get_json(url, headers=self._headers())
        except CollectorHTTPError as e:
            logger.info("Solana Tracker PnL fetch miss for %s/%s: %s", wallet_address, token_address, e)
            return None

        try:
            realized = _to_float(payload.get("realized") or payload.get("realizedPnl") or payload.get("pnl"))
            unrealized = _to_float(payload.get("unrealized") or payload.get("unrealizedPnl"))
            roi_pct = _to_float(payload.get("percentageChange") or payload.get("roi") or payload.get("pnlPercent"))
            total_bought_usd = _to_float(payload.get("totalBoughtUsd") or payload.get("totalInvested"))
            total_pnl = None
            if realized is not None or unrealized is not None:
                total_pnl = (realized or 0.0) + (unrealized or 0.0)
            return {
                "realized_pnl_usd": realized,
                "unrealized_pnl_usd": unrealized,
                "total_pnl_usd": total_pnl,
                "roi_pct": roi_pct,
                "total_bought_usd": total_bought_usd,
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed parsing Solana Tracker PnL for %s/%s: %s", wallet_address, token_address, e)
            return None


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
