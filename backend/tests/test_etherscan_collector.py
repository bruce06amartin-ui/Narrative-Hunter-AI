from unittest.mock import patch

from app.collectors.etherscan import EtherscanCollector
from app.config import settings

# Fixture shape confirmed against https://docs.etherscan.io/api-reference/endpoint/tokentx
TOKENTX_FIXTURE = {
    "status": "1",
    "message": "OK",
    "result": [
        {
            "blockNumber": "4730207",
            "timeStamp": "1700000000",
            "hash": "0xabc123",
            "nonce": "406",
            "blockHash": "0xdeadbeef",
            "from": "0xFrom00000000000000000000000000000000001",
            "contractAddress": "0xTokenContract0000000000000000000000001",
            "to": "0xTo000000000000000000000000000000000001",
            "value": "1000000000000000000000",
            "tokenName": "TestMeme",
            "tokenSymbol": "TMEME",
            "tokenDecimal": "18",
            "transactionIndex": "81",
            "gas": "940000",
            "gasPrice": "32010000000",
            "gasUsed": "77759",
            "cumulativeGasUsed": "2523379",
            "confirmations": "18737452",
        }
    ],
}

NO_TX_FIXTURE = {"status": "0", "message": "No transactions found", "result": []}


def test_get_token_transfers_requires_api_key():
    collector = EtherscanCollector()
    settings.etherscan_api_key = None
    assert collector.get_token_transfers("eth", "0xabc") == []


def test_get_token_transfers_normalizes_fixture():
    collector = EtherscanCollector()
    settings.etherscan_api_key = "fake-key-for-test"
    with patch("app.collectors.etherscan.get_json", return_value=TOKENTX_FIXTURE):
        transfers = collector.get_token_transfers("eth", "0xTokenContract0000000000000000000000001")

    assert len(transfers) == 1
    t = transfers[0]
    assert t["tx_hash"] == "0xabc123"
    assert t["from_address"] == "0xfrom00000000000000000000000000000000001"
    assert t["to_address"] == "0xto000000000000000000000000000000000001"
    assert t["amount"] == 1000.0  # 1e21 / 10^18
    assert t["block_number"] == 4730207


def test_get_token_transfers_unsupported_chain_returns_empty():
    collector = EtherscanCollector()
    settings.etherscan_api_key = "fake-key-for-test"
    assert collector.get_token_transfers("solana", "someaddress") == []


def test_get_token_transfers_no_tx_returns_empty_not_error():
    collector = EtherscanCollector()
    settings.etherscan_api_key = "fake-key-for-test"
    with patch("app.collectors.etherscan.get_json", return_value=NO_TX_FIXTURE):
        transfers = collector.get_token_transfers("eth", "0xTokenContract0000000000000000000000001")
    assert transfers == []
