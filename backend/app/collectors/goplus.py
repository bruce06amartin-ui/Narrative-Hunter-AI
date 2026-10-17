"""
GoPlus Security collector (MODULE 5: Rug Detection).

Docs:
  EVM:    https://docs.gopluslabs.io/reference/tokensecurityusingget_1
          field reference: https://docs.gopluslabs.io/reference/response-details
  Solana: https://docs.gopluslabs.io/reference/solanatokensecurityusingget
          field reference: https://docs.gopluslabs.io/reference/response-detail-1

No API key required for the public tier. Field names below were verified
directly against GoPlus's published field reference pages (not guessed from
memory), but the API is versioned independently of this codebase - if a
field ever comes back missing/renamed, `_to_bool`/`.get()` fail safe to
`None` rather than raising, so a schema drift degrades a single flag
instead of crashing a whole risk-check cycle.
"""

import logging

from app.chains import EVM_GOPLUS_CHAIN_IDS as EVM_CHAIN_IDS
from app.collectors.base import get_json, CollectorHTTPError

logger = logging.getLogger(__name__)

EVM_BASE_URL = "https://api.gopluslabs.io/api/v1/token_security"
SOLANA_URL = "https://api.gopluslabs.io/api/v1/solana/token_security"

# GoPlus chain_id values now live in app/chains.py (EVM_GOPLUS_CHAIN_IDS) so
# the Etherscan collector can share the same source of truth where the
# values happen to align. Full GoPlus list: https://docs.gopluslabs.io/reference/getchainslistusingget


class GoPlusCollector:
    name = "goplus"

    def check_token(self, chain: str, contract_address: str) -> dict | None:
        """Fetch and normalize security data for one token. Returns None if
        the chain isn't supported or the upstream call fails - callers treat
        a None as "no data available", not "token is safe"."""
        chain_key = chain.lower()
        if chain_key == "solana":
            return self._check_solana(contract_address)
        if chain_key in EVM_CHAIN_IDS:
            return self._check_evm(EVM_CHAIN_IDS[chain_key], contract_address)

        logger.info("GoPlus: unsupported chain '%s', skipping risk check", chain)
        return None

    # ---- EVM (Ethereum, Base, ...) ----

    def _check_evm(self, chain_id: str, contract_address: str) -> dict | None:
        url = f"{EVM_BASE_URL}/{chain_id}"
        try:
            payload = get_json(url, params={"contract_addresses": contract_address})
        except CollectorHTTPError as e:
            logger.warning("GoPlus EVM lookup failed for %s: %s", contract_address, e)
            return None

        result = payload.get("result", {})
        # GoPlus keys the result dict by lowercased contract address
        data = result.get(contract_address.lower()) or result.get(contract_address)
        if not data:
            return None

        holders = data.get("holders") or []
        top10_holder_percent = _sum_percent(holders[:10])

        lp_holders = data.get("lp_holders") or []
        lp_locked_percent = _sum_percent([h for h in lp_holders if _to_bool(h.get("is_locked"))])
        lp_total_percent = _sum_percent(lp_holders)

        return {
            "chain_type": "evm",
            "is_open_source": _to_bool(data.get("is_open_source")),
            "is_proxy": _to_bool(data.get("is_proxy")),
            "is_mintable": _to_bool(data.get("is_mintable")),
            "owner_address": data.get("owner_address"),
            "creator_address": data.get("creator_address"),
            "can_take_back_ownership": _to_bool(data.get("can_take_back_ownership")),
            "owner_change_balance": _to_bool(data.get("owner_change_balance")),
            "hidden_owner": _to_bool(data.get("hidden_owner")),
            "selfdestruct": _to_bool(data.get("selfdestruct")),
            "external_call": _to_bool(data.get("external_call")),
            "is_honeypot": _to_bool(data.get("is_honeypot")),
            "cannot_sell_all": _to_bool(data.get("cannot_sell_all")),
            "is_blacklisted": _to_bool(data.get("is_blacklisted")),
            "transfer_pausable": _to_bool(data.get("transfer_pausable")),
            "slippage_modifiable": _to_bool(data.get("slippage_modifiable")),
            "trading_cooldown": _to_bool(data.get("trading_cooldown")),
            "anti_whale_modifiable": _to_bool(data.get("anti_whale_modifiable")),
            "buy_tax": _to_float(data.get("buy_tax")),
            "sell_tax": _to_float(data.get("sell_tax")),
            "owner_percent": _to_float(data.get("owner_percent")),
            "creator_percent": _to_float(data.get("creator_percent")),
            "top10_holder_percent": top10_holder_percent,
            "lp_locked_percent": lp_locked_percent if lp_total_percent else None,
            "holder_count": _to_int(data.get("holder_count")),
        }

    # ---- Solana ----

    def _check_solana(self, contract_address: str) -> dict | None:
        try:
            payload = get_json(SOLANA_URL, params={"contract_addresses": contract_address})
        except CollectorHTTPError as e:
            logger.warning("GoPlus Solana lookup failed for %s: %s", contract_address, e)
            return None

        result = payload.get("result", {})
        data = result.get(contract_address)
        if not data:
            return None

        holders = data.get("holders") or []
        top10_holder_percent = _sum_percent(holders[:10])

        lp_holders = _extract_solana_lp_holders(data)
        lp_locked_percent = _sum_percent([h for h in lp_holders if _to_bool(h.get("is_locked"))])
        lp_total_percent = _sum_percent(lp_holders)

        return {
            "chain_type": "solana",
            "is_mintable": _to_bool(_status(data.get("mintable"))),
            "mint_authority": _authority_address(data.get("mintable")),
            "is_freezable": _to_bool(_status(data.get("freezable"))),
            "is_closable": _to_bool(_status(data.get("closable"))),
            "balance_mutable": _to_bool(_status(data.get("balance_mutable_authority"))),
            "metadata_mutable": _to_bool(_status(data.get("metadata_mutable"))),
            "non_transferable": _to_bool(data.get("non_transferable")),
            "trusted_token": _to_bool(data.get("trusted_token")),
            # Solana has no single "creator" field like EVM's creator_address;
            # mint authority is the closest equivalent for repeat-deployer
            # detection (MODULE 5) - often the same wallet that deployed the token.
            "creator_address": _authority_address(data.get("mintable")),
            "top10_holder_percent": top10_holder_percent,
            "lp_locked_percent": lp_locked_percent if lp_total_percent else None,
            "holder_count": None,  # not provided in the Solana basic-info schema
        }


def _extract_solana_lp_holders(data: dict) -> list[dict]:
    """Solana's lp_holders live nested under each DEX pool entry, not at the
    top level like the EVM response. Flatten across all pools found."""
    lp_holders: list[dict] = []
    for pool in data.get("dex") or []:
        lp_holders.extend(pool.get("lp_holders") or [])
    return lp_holders


def _status(field: dict | None) -> str | None:
    if not isinstance(field, dict):
        return None
    return field.get("status")


def _authority_address(field: dict | None) -> str | None:
    if not isinstance(field, dict):
        return None
    authority = field.get("authority")
    if isinstance(authority, dict):
        return authority.get("address")
    return None


def _sum_percent(holders: list[dict]) -> float | None:
    if not holders:
        return None
    total = 0.0
    found = False
    for h in holders:
        pct = _to_float(h.get("percent"))
        if pct is not None:
            total += pct
            found = True
    return (total * 100) if found else None  # GoPlus reports 1 = 100%


def _to_bool(value) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value) == "1"


def _to_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
