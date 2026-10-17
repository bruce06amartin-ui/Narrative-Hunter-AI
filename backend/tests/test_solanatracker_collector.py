from unittest.mock import patch

from app.collectors.solanatracker import SolanaTrackerCollector

SAMPLE_HOLDERS_RESPONSE = {
    "accounts": [
        {"address": "WalletAAA111", "percentage": 5.2},
        {"address": "WalletBBB222", "percentage": 3.1},
        {"address": "WalletCCC333", "percentage": 2.8},
    ]
}

SAMPLE_PNL_RESPONSE = {
    "realized": 120.5,
    "unrealized": 30.0,
    "percentageChange": 45.2,
    "totalBoughtUsd": 500.0,
}


def make_collector():
    return SolanaTrackerCollector()


def test_is_configured_true_with_key():
    collector = make_collector()
    with patch("app.collectors.solanatracker.settings.solanatracker_api_key", "fake-key"):
        assert collector.is_configured() is True


def test_is_configured_false_without_key():
    collector = make_collector()
    with patch("app.collectors.solanatracker.settings.solanatracker_api_key", None):
        assert collector.is_configured() is False


def test_get_top_holders_parses_correctly():
    collector = make_collector()
    with patch("app.collectors.solanatracker.settings.solanatracker_api_key", "fake-key"), \
         patch("app.collectors.solanatracker.get_json", return_value=SAMPLE_HOLDERS_RESPONSE):
        holders = collector.get_top_holders("SomeTokenMintAddress", limit=10)

    assert len(holders) == 3
    assert holders[0]["address"] == "WalletAAA111"
    assert holders[0]["percentage"] == 5.2


def test_get_top_holders_respects_limit():
    collector = make_collector()
    with patch("app.collectors.solanatracker.settings.solanatracker_api_key", "fake-key"), \
         patch("app.collectors.solanatracker.get_json", return_value=SAMPLE_HOLDERS_RESPONSE):
        holders = collector.get_top_holders("SomeTokenMintAddress", limit=2)

    assert len(holders) == 2


def test_get_top_holders_not_configured_returns_empty_no_call():
    collector = make_collector()
    with patch("app.collectors.solanatracker.settings.solanatracker_api_key", None), \
         patch("app.collectors.solanatracker.get_json") as mock_get:
        holders = collector.get_top_holders("SomeTokenMintAddress")
    assert holders == []
    mock_get.assert_not_called()


def test_get_top_holders_handles_api_failure():
    from app.collectors.base import CollectorHTTPError
    collector = make_collector()
    with patch("app.collectors.solanatracker.settings.solanatracker_api_key", "fake-key"), \
         patch("app.collectors.solanatracker.get_json", side_effect=CollectorHTTPError("boom")):
        holders = collector.get_top_holders("SomeTokenMintAddress")
    assert holders == []


def test_get_top_holders_skips_entries_without_address():
    collector = make_collector()
    broken_response = {"accounts": [{"percentage": 5.0}, {"address": "ValidWallet", "percentage": 1.0}]}
    with patch("app.collectors.solanatracker.settings.solanatracker_api_key", "fake-key"), \
         patch("app.collectors.solanatracker.get_json", return_value=broken_response):
        holders = collector.get_top_holders("SomeTokenMintAddress")
    assert len(holders) == 1
    assert holders[0]["address"] == "ValidWallet"


def test_get_wallet_token_pnl_parses_correctly():
    collector = make_collector()
    with patch("app.collectors.solanatracker.settings.solanatracker_api_key", "fake-key"), \
         patch("app.collectors.solanatracker.get_json", return_value=SAMPLE_PNL_RESPONSE):
        pnl = collector.get_wallet_token_pnl("SomeWallet", "SomeTokenMintAddress")

    assert pnl is not None
    assert pnl["realized_pnl_usd"] == 120.5
    assert pnl["unrealized_pnl_usd"] == 30.0
    assert pnl["total_pnl_usd"] == 150.5
    assert pnl["roi_pct"] == 45.2


def test_get_wallet_token_pnl_handles_partial_data():
    collector = make_collector()
    partial = {"realized": 80.0, "percentageChange": 20.0}
    with patch("app.collectors.solanatracker.settings.solanatracker_api_key", "fake-key"), \
         patch("app.collectors.solanatracker.get_json", return_value=partial):
        pnl = collector.get_wallet_token_pnl("SomeWallet", "SomeTokenMintAddress")

    assert pnl["total_pnl_usd"] == 80.0


def test_get_wallet_token_pnl_api_failure_returns_none():
    from app.collectors.base import CollectorHTTPError
    collector = make_collector()
    with patch("app.collectors.solanatracker.settings.solanatracker_api_key", "fake-key"), \
         patch("app.collectors.solanatracker.get_json", side_effect=CollectorHTTPError("boom")):
        pnl = collector.get_wallet_token_pnl("SomeWallet", "SomeTokenMintAddress")
    assert pnl is None
