from unittest.mock import patch

from app.collectors.geckoterminal import GeckoTerminalCollector

SAMPLE_MULTI_RESPONSE = {
    "data": [
        {
            "id": "eth_0xpool1",
            "type": "pool",
            "attributes": {
                "address": "0xpool1",
                "base_token_price_usd": "0.005",
                "reserve_in_usd": "150000.0",
                "market_cap_usd": "500000.0",
                "fdv_usd": "500000.0",
                "pool_created_at": "2026-07-23T10:00:00Z",
                "volume_usd": {"h24": "12345.67"},
                "price_change_percentage": {"h1": "1.5", "h24": "-3.2"},
            },
            "relationships": {
                "base_token": {"data": {"id": "eth_0xtoken1", "type": "token"}},
            },
        },
        {
            "id": "eth_0xpool2",
            "type": "pool",
            "attributes": {
                "address": "0xpool2",
                "base_token_price_usd": "1.25",
                "reserve_in_usd": "80000.0",
                "market_cap_usd": None,
                "fdv_usd": "90000.0",
                "pool_created_at": "2026-07-23T11:00:00Z",
                "volume_usd": {"h24": "999.0"},
                "price_change_percentage": {"h1": "0.1", "h24": "5.0"},
            },
            "relationships": {
                "base_token": {"data": {"id": "eth_0xtoken2", "type": "token"}},
            },
        },
    ],
    "included": [
        {
            "id": "eth_0xtoken1",
            "type": "token",
            "attributes": {"address": "0xtoken1", "symbol": "AAA", "name": "Token AAA"},
        },
        {
            "id": "eth_0xtoken2",
            "type": "token",
            "attributes": {"address": "0xtoken2", "symbol": "BBB", "name": "Token BBB"},
        },
    ],
}


def make_collector():
    return GeckoTerminalCollector(networks=["eth"])


# All tests patch time.sleep - refresh_prices now deliberately paces itself
# proportional to batch size (real fix for observed 429s), which would
# otherwise make these tests genuinely slow to run.

def test_refresh_prices_parses_multiple_pools():
    collector = make_collector()
    with patch("app.collectors.geckoterminal.get_json", return_value=SAMPLE_MULTI_RESPONSE), \
         patch("app.collectors.geckoterminal.time.sleep") as mock_sleep:
        results = collector.refresh_prices("eth", ["0xpool1", "0xpool2"])

    assert len(results) == 2
    first, second = results
    assert first["pair_address"] == "0xpool1"
    assert first["contract_address"] == "0xtoken1"
    assert first["symbol"] == "AAA"
    assert first["liquidity_usd"] == 150000.0
    assert first["price_usd"] == 0.005
    assert first["price_change_24h"] == -3.2

    assert second["pair_address"] == "0xpool2"
    assert second["market_cap_usd"] is None
    # 2 addresses -> should pace for (2-1)*2.2 = 2.2s
    mock_sleep.assert_called_once()
    assert abs(mock_sleep.call_args[0][0] - 2.2) < 0.01


def test_refresh_prices_single_address_does_not_sleep():
    """Only 1 address in the batch - no pacing needed since there's nothing
    else in this same call to space out against."""
    collector = make_collector()
    with patch("app.collectors.geckoterminal.get_json", return_value=SAMPLE_MULTI_RESPONSE), \
         patch("app.collectors.geckoterminal.time.sleep") as mock_sleep:
        collector.refresh_prices("eth", ["0xpool1"])
    mock_sleep.assert_not_called()


def test_refresh_prices_scales_pacing_with_batch_size():
    collector = make_collector()
    with patch("app.collectors.geckoterminal.get_json", return_value={"data": [], "included": []}), \
         patch("app.collectors.geckoterminal.time.sleep") as mock_sleep:
        collector.refresh_prices("eth", [f"0xpool{i}" for i in range(30)])
    # 30 addresses -> (30-1)*2.2 = 63.8s
    assert abs(mock_sleep.call_args[0][0] - 63.8) < 0.01


def test_refresh_prices_empty_input_returns_empty_no_api_call():
    collector = make_collector()
    with patch("app.collectors.geckoterminal.get_json") as mock_get, \
         patch("app.collectors.geckoterminal.time.sleep") as mock_sleep:
        results = collector.refresh_prices("eth", [])
    assert results == []
    mock_get.assert_not_called()
    mock_sleep.assert_not_called()


def test_refresh_prices_caps_at_30_addresses():
    collector = make_collector()
    many_addresses = [f"0xpool{i}" for i in range(50)]
    with patch("app.collectors.geckoterminal.get_json", return_value={"data": [], "included": []}) as mock_get, \
         patch("app.collectors.geckoterminal.time.sleep"):
        collector.refresh_prices("eth", many_addresses)

    called_url = mock_get.call_args[0][0]
    assert "0xpool29" in called_url
    assert "0xpool30" not in called_url


def test_refresh_prices_api_failure_returns_empty_list_not_raise():
    from app.collectors.base import CollectorHTTPError
    collector = make_collector()
    with patch("app.collectors.geckoterminal.get_json", side_effect=CollectorHTTPError("boom")), \
         patch("app.collectors.geckoterminal.time.sleep"):
        results = collector.refresh_prices("eth", ["0xpool1"])
    assert results == []


def test_refresh_prices_skips_malformed_pool_without_crashing():
    collector = make_collector()
    broken_response = {
        "data": [
            {"id": "bad", "type": "pool", "attributes": None},
            SAMPLE_MULTI_RESPONSE["data"][0],
        ],
        "included": SAMPLE_MULTI_RESPONSE["included"],
    }
    with patch("app.collectors.geckoterminal.get_json", return_value=broken_response), \
         patch("app.collectors.geckoterminal.time.sleep"):
        results = collector.refresh_prices("eth", ["bad", "0xpool1"])
    assert len(results) == 1
    assert results[0]["pair_address"] == "0xpool1"
