"""
Tests for the manipulation sanity check in SolanaWalletIntelligenceService.

The actual filter is a SQLAlchemy query condition (see check_all_active),
not a standalone Python function - these tests mirror that exact logic in
plain Python to verify the reasoning and threshold values are sound, and
to catch any future regression if the thresholds change. Real-world
trigger: production data showing a coin with $180,626,494 claimed
liquidity and only $2,099 in 24h volume (~86,000:1 ratio) - a known DeFi
manipulation pattern (fake reserves reported to indexers).
"""

from app.services.solana_wallet_service import (
    MANIPULATION_CHECK_MIN_LIQUIDITY_USD,
    MIN_VOLUME_TO_LIQUIDITY_RATIO,
)


def passes_sanity_filter(liquidity_usd: float, volume_24h_usd: float | None) -> bool:
    if liquidity_usd < MANIPULATION_CHECK_MIN_LIQUIDITY_USD:
        return True
    if volume_24h_usd is None:
        return True
    return volume_24h_usd >= liquidity_usd * MIN_VOLUME_TO_LIQUIDITY_RATIO


def test_real_manipulated_coin_from_production_data_is_excluded():
    assert passes_sanity_filter(180_626_494.37, 2_099.30) is False


def test_legitimate_large_coin_with_realistic_volume_passes():
    assert passes_sanity_filter(5_000_000, 50_000) is True


def test_small_coin_always_passes_regardless_of_volume():
    assert passes_sanity_filter(500_000, 10) is True
    assert passes_sanity_filter(500_000, 0) is True


def test_unknown_volume_gets_benefit_of_the_doubt():
    assert passes_sanity_filter(50_000_000, None) is True


def test_borderline_case_at_exact_ratio_threshold_passes():
    assert passes_sanity_filter(1_000_000, 500) is True


def test_just_below_ratio_threshold_fails():
    assert passes_sanity_filter(1_000_000, 499.99) is False


def test_extreme_manipulation_ratio_is_caught():
    assert passes_sanity_filter(1_000_000_000, 1.0) is False
