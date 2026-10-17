"""
Etherscan collector (MODULE 3: Wallet Intelligence - EVM chains only).

Docs: https://docs.etherscan.io/etherscan-v2 (unified multichain API)
Endpoint: GET https://api.etherscan.io/v2/api?chainid={id}&module=account&action=tokentx
Field reference verified against: https://docs.etherscan.io/api-reference/endpoint/tokentx

Requires a free ETHERSCAN_API_KEY (unlike GeckoTerminal/DexScreener/GoPlus,
Etherscan does not offer a keyless tier). If unset, this collector is
skipped entirely and wallet intelligence simply isn't computed for any
coin - see wallet_service.py for how that's surfaced rather than hidden.

Etherscan's V1 API (the old per-chain domains like api.basescan.org) was
deprecated 2025-08-15 - this collector only targets the V2 unified endpoint.
"""

import logging
from datetime import datetime, timezone

from app.chains import EVM_ETHERSCAN_CHAIN_IDS
from app.collectors.base import get_json, CollectorHTTPError
from app.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.etherscan.io/v2/api"


class EtherscanCollector:
    name = "etherscan"

    def is_configured(self) -> bool:
        return bool(settings.etherscan_api_key)

    def get_token_transfers(
        self, chain: str, contract_address: str, offset: int = 500
    ) -> list[dict]:
        """Fetch the most recent ERC20 transfer events for a token contract.
        Returns [] (not an error) if the chain isn't EVM-supported, the API
        key isn't configured, or the call fails - callers treat that as
        "no wallet data available," matching the rest of this codebase's
        pattern for optional external data sources."""
        if not self.is_configured():
            return []

        chain_id = EVM_ETHERSCAN_CHAIN_IDS.get(chain.lower())
        if chain_id is None:
            return []

        params = {
            "chainid": chain_id,
            "module": "account",
            "action": "tokentx",
            "contractaddress": contract_address,
            "page": 1,
            "offset": offset,
            "sort": "desc",
            "apikey": settings.etherscan_api_key,
        }

        try:
            payload = get_json(BASE_URL, params=params)
        except CollectorHTTPError as e:
            logger.warning("Etherscan tokentx failed for %s/%s: %s", chain, contract_address, e)
            return []

        if payload.get("status") != "1":
            # status "0" with message "No transactions found" is a normal,
            # expected case for a very new token - not an error worth logging loudly.
            if payload.get("message") not in ("No transactions found", None):
                logger.info("Etherscan tokentx non-OK for %s/%s: %s", chain, contract_address, payload.get("message"))
            return []

        transfers = []
        for row in payload.get("result", []):
            try:
                transfers.append(self._normalize(row))
            except Exception as e:  # noqa: BLE001
                logger.warning("Skipping malformed Etherscan transfer row: %s", e)
        return transfers

    def _normalize(self, row: dict) -> dict:
        decimals = int(row.get("tokenDecimal") or 18)
        raw_value = int(row.get("value") or 0)
        amount = raw_value / (10 ** decimals)

        return {
            "tx_hash": row["hash"],
            "from_address": row["from"].lower(),
            "to_address": row["to"].lower(),
            "amount": amount,
            "block_number": int(row.get("blockNumber") or 0),
            "timestamp": datetime.fromtimestamp(int(row["timeStamp"]), tz=timezone.utc),
        }
