from unittest.mock import patch

from app.collectors.goplus import GoPlusCollector

EVM_ADDRESS = "0xabc0000000000000000000000000000000dead"

EVM_FIXTURE = {
    "code": 1,
    "message": "OK",
    "result": {
        EVM_ADDRESS: {
            "is_open_source": "1",
            "is_proxy": "0",
            "is_mintable": "1",
            "owner_address": "0xowner",
            "can_take_back_ownership": "0",
            "owner_change_balance": "0",
            "hidden_owner": "1",
            "selfdestruct": "0",
            "external_call": "0",
            "is_honeypot": "0",
            "cannot_sell_all": "0",
            "is_blacklisted": "0",
            "transfer_pausable": "0",
            "slippage_modifiable": "0",
            "trading_cooldown": "0",
            "anti_whale_modifiable": "0",
            "buy_tax": "0.05",
            "sell_tax": "0.30",
            "owner_percent": "0.02",
            "creator_percent": "0.1",
            "holder_count": "1200",
            "holders": [
                {"address": "0x1", "percent": "0.15", "is_locked": "0"},
                {"address": "0x2", "percent": "0.10", "is_locked": "0"},
            ],
            "lp_holders": [
                {"address": "0xlp1", "percent": "0.6", "is_locked": "1"},
                {"address": "0xlp2", "percent": "0.4", "is_locked": "0"},
            ],
        }
    },
}

SOLANA_ADDRESS = "SoMeToKenMintAddress11111111111111111111111"

SOLANA_FIXTURE = {
    "code": 1,
    "message": "OK",
    "result": {
        SOLANA_ADDRESS: {
            "mintable": {"status": "1", "authority": {"address": "MintAuth111"}},
            "freezable": {"status": "0", "authority": None},
            "closable": {"status": "0"},
            "balance_mutable_authority": {"status": "0"},
            "metadata_mutable": {"status": "1"},
            "non_transferable": "0",
            "trusted_token": None,
            "holders": [
                {"token_account": "acc1", "percent": "0.5", "is_locked": "0"},
                {"token_account": "acc2", "percent": "0.1", "is_locked": "0"},
            ],
            "dex": [
                {
                    "dexname": "Raydium",
                    "lp_holders": [
                        {"address": "lp1", "percent": "0.2", "is_locked": "1"},
                        {"address": "lp2", "percent": "0.8", "is_locked": "0"},
                    ],
                }
            ],
        }
    },
}


def test_check_evm_normalizes_expected_fields():
    collector = GoPlusCollector()
    with patch("app.collectors.goplus.get_json", return_value=EVM_FIXTURE):
        result = collector.check_token("eth", EVM_ADDRESS)

    assert result is not None
    assert result["chain_type"] == "evm"
    assert result["is_mintable"] is True
    assert result["hidden_owner"] is True
    assert result["is_honeypot"] is False
    assert result["sell_tax"] == 0.30
    assert result["top10_holder_percent"] == 25.0  # 0.15 + 0.10, *100
    assert result["lp_locked_percent"] == 60.0  # only lp1 locked, 0.6 * 100


def test_check_solana_normalizes_expected_fields():
    collector = GoPlusCollector()
    with patch("app.collectors.goplus.get_json", return_value=SOLANA_FIXTURE):
        result = collector.check_token("solana", SOLANA_ADDRESS)

    assert result is not None
    assert result["chain_type"] == "solana"
    assert result["is_mintable"] is True
    assert result["mint_authority"] == "MintAuth111"
    assert result["is_freezable"] is False
    assert result["top10_holder_percent"] == 60.0  # 0.5 + 0.1, *100
    assert result["lp_locked_percent"] == 20.0  # only lp1 locked, 0.2 * 100


def test_check_token_unsupported_chain_returns_none():
    collector = GoPlusCollector()
    assert collector.check_token("some_unknown_chain", "0xdead") is None


def test_check_token_missing_result_returns_none():
    collector = GoPlusCollector()
    with patch("app.collectors.goplus.get_json", return_value={"code": 1, "result": {}}):
        assert collector.check_token("eth", EVM_ADDRESS) is None
