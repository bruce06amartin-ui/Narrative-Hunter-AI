from unittest.mock import MagicMock

from app.services.pool_migration_service import PoolMigrationService


class FakeCoin:
    def __init__(self, liquidity_usd=1000.0, pair_address="0xold_pool", chain="eth"):
        self.id = "coin-1"
        self.symbol = "TEST"
        self.contract_address = "0xtoken123"
        self.chain = chain
        self.pair_address = pair_address
        self.liquidity_usd = liquidity_usd
        self.volume_24h_usd = None
        self.price_usd = None
        self.market_cap_usd = None
        self.fdv_usd = None
        self.price_change_1h = None
        self.price_change_24h = None
        self.last_updated_at = None


def make_service():
    return PoolMigrationService(db=MagicMock(), collector=MagicMock())


def test_no_pools_found_no_migration():
    service = make_service()
    coin = FakeCoin()
    service.collector.get_all_pools_for_token.return_value = []

    assert service._check_and_migrate(coin) is False
    assert coin.pair_address == "0xold_pool"


def test_already_on_best_pool_no_migration():
    service = make_service()
    coin = FakeCoin(liquidity_usd=50_000.0, pair_address="0xbest_pool")
    service.collector.get_all_pools_for_token.return_value = [
        {"pair_address": "0xbest_pool", "liquidity_usd": 50_000.0}
    ]

    assert service._check_and_migrate(coin) is False


def test_improvement_below_threshold_no_migration():
    """Real-world case this guards against: a coin with $1,000 liquidity
    finding an 'alternate' pool at $2,000 - genuinely bigger, but not the
    3x improvement required to be confident this is a real migration
    rather than noise between near-identical thin pools."""
    service = make_service()
    coin = FakeCoin(liquidity_usd=1000.0, pair_address="0xold_pool")
    service.collector.get_all_pools_for_token.return_value = [
        {"pair_address": "0xold_pool", "liquidity_usd": 1000.0},
        {"pair_address": "0xslightly_better", "liquidity_usd": 2000.0},
    ]

    assert service._check_and_migrate(coin) is False
    assert coin.pair_address == "0xold_pool"


def test_genuine_migration_updates_all_fields():
    """The exact real-world scenario this service exists for: a coin
    discovered on a thin, near-dead pool ($500) that has genuinely
    migrated to a much healthier pool ($75,000, 150x improvement) -
    should switch and update every relevant field."""
    service = make_service()
    coin = FakeCoin(liquidity_usd=500.0, pair_address="0xthin_dead_pool")
    new_pool = {
        "pair_address": "0xhealthy_pool",
        "liquidity_usd": 75_000.0,
        "volume_24h_usd": 12_000.0,
        "price_usd": 0.0042,
        "market_cap_usd": 420_000.0,
        "fdv_usd": 500_000.0,
        "price_change_1h": 3.5,
        "price_change_24h": 18.2,
    }
    service.collector.get_all_pools_for_token.return_value = [
        {"pair_address": "0xthin_dead_pool", "liquidity_usd": 500.0},
        new_pool,
    ]

    result = service._check_and_migrate(coin)

    assert result is True
    assert coin.pair_address == "0xhealthy_pool"
    assert coin.liquidity_usd == 75_000.0
    assert coin.volume_24h_usd == 12_000.0
    assert coin.price_usd == 0.0042
    assert coin.market_cap_usd == 420_000.0


def test_no_contract_address_no_migration():
    service = make_service()
    coin = FakeCoin()
    coin.contract_address = None

    assert service._check_and_migrate(coin) is False
    service.collector.get_all_pools_for_token.assert_not_called()
