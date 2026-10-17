"""
Shared chain identifiers so collectors don't each maintain their own
slightly-different mapping. Two different numbering schemes are in play:

- GoPlus uses its own chain_id scheme (see EVM_GOPLUS_CHAIN_IDS).
- Etherscan's unified V2 API uses the actual EVM chain ID (see
  EVM_ETHERSCAN_CHAIN_IDS) - these happen to match GoPlus's for the chains
  this platform discovers on (eth=1, base=8453), but that's not guaranteed
  for every chain, so they're kept as separate maps rather than merged.
"""

EVM_GOPLUS_CHAIN_IDS = {
    "eth": "1",
    "ethereum": "1",
    "base": "8453",
}

EVM_ETHERSCAN_CHAIN_IDS = {
    "eth": 1,
    "ethereum": 1,
    "base": 8453,
}

# Chains this platform can fetch on-chain wallet/transfer data for (MODULE 3).
# Solana isn't here - see wallet_service.py docstring for why.
EVM_WALLET_SUPPORTED_CHAINS = set(EVM_ETHERSCAN_CHAIN_IDS.keys())
