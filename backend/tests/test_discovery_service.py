from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.discovery_service import DiscoveryService


def make_service():
    service = DiscoveryService.__new__(DiscoveryService)
    service.db = MagicMock()
    return service


def make_coin(**overrides):
    defaults = dict(
        id="coin-1", liquidity_usd=100.0, market_cap_usd=200.0, fdv_usd=200.0,
        volume_24h_usd=50.0, price_usd=0.001, price_change_1h=1.0, price_change_24h=2.0,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_apply_price_update_overwrites_all_present_fields():
    service = make_service()
    coin = make_coin()
    fresh_data = {
        "liquidity_usd": 999.0,
        "market_cap_usd": 888.0,
        "fdv_usd": 888.0,
        "volume_24h_usd": 777.0,
        "price_usd": 0.005,
        "price_change_1h": 10.0,
        "price_change_24h": 20.0,
    }
    service._apply_price_update(coin, fresh_data)

    assert coin.liquidity_usd == 999.0
    assert coin.market_cap_usd == 888.0
    assert coin.price_usd == 0.005
    assert coin.price_change_24h == 20.0


def test_apply_price_update_preserves_existing_value_when_field_missing():
    service = make_service()
    coin = make_coin(market_cap_usd=555.0)
    fresh_data = {
        "liquidity_usd": 999.0,
        "market_cap_usd": None,
        "fdv_usd": 888.0,
        "volume_24h_usd": 777.0,
        "price_usd": 0.005,
        "price_change_1h": 10.0,
        "price_change_24h": 20.0,
    }
    service._apply_price_update(coin, fresh_data)

    assert coin.liquidity_usd == 999.0
    assert coin.market_cap_usd == 555.0


def test_apply_price_update_calls_record_price_history():
    service = make_service()
    service._record_price_history = MagicMock()
    coin = make_coin()

    service._apply_price_update(coin, {"price_usd": 0.01})

    service._record_price_history.assert_called_once_with(coin)
