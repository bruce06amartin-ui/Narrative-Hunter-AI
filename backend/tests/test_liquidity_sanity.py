from app.services.liquidity_sanity import is_liquidity_plausible, is_actively_trading


# --- is_liquidity_plausible ---

def test_plausible_real_manipulated_case_from_production():
    assert is_liquidity_plausible(180_626_494.37, 2_099.30) is False


def test_plausible_legitimate_large_coin():
    assert is_liquidity_plausible(5_000_000, 50_000) is True


def test_plausible_small_coin_always_passes():
    assert is_liquidity_plausible(500_000, 0) is True


def test_plausible_unknown_volume_gets_benefit_of_doubt():
    assert is_liquidity_plausible(50_000_000, None) is True


# --- is_actively_trading ---

def test_actively_trading_real_dead_coin_case():
    """The exact real-world case that prompted this function: a small,
    legitimate (non-manipulated) coin whose real trading has stopped."""
    assert is_actively_trading(5.0) is False


def test_actively_trading_healthy_volume_passes():
    assert is_actively_trading(500.0) is True


def test_actively_trading_exactly_at_threshold_passes():
    assert is_actively_trading(50.0) is True


def test_actively_trading_just_below_threshold_fails():
    assert is_actively_trading(49.99) is False


def test_actively_trading_zero_volume_fails():
    assert is_actively_trading(0.0) is False


def test_actively_trading_unknown_volume_gets_benefit_of_doubt():
    assert is_actively_trading(None) is True
