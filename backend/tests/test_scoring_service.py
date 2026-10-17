from app.services.scoring_service import ScoringService, LIQUIDITY_SATURATION_USD


class DummyCoin:
    def __init__(self, liquidity_usd=0.0, volume_24h_usd=None):
        self.liquidity_usd = liquidity_usd
        self.volume_24h_usd = volume_24h_usd


def test_liquidity_score_zero_liquidity():
    service = ScoringService(db=None)
    coin = DummyCoin(liquidity_usd=0.0)
    assert service._liquidity_score(coin) == 0.0


def test_liquidity_score_at_saturation():
    service = ScoringService(db=None)
    coin = DummyCoin(liquidity_usd=LIQUIDITY_SATURATION_USD)
    score = service._liquidity_score(coin)
    assert 99.0 <= score <= 100.0


def test_liquidity_score_monotonic():
    service = ScoringService(db=None)
    low = service._liquidity_score(DummyCoin(liquidity_usd=1_000))
    high = service._liquidity_score(DummyCoin(liquidity_usd=100_000))
    assert high > low


def test_liquidity_score_none_for_real_manipulated_coin_from_production():
    """The exact real-world case that prompted this fix: $183M claimed
    liquidity, $0 volume."""
    service = ScoringService(db=None)
    coin = DummyCoin(liquidity_usd=183_755_797.97, volume_24h_usd=0.0)
    assert service._liquidity_score(coin) is None


def test_liquidity_score_real_for_legitimate_large_coin():
    """A large coin with a realistic volume-to-liquidity ratio should
    still get a real, confident score - the check should never penalize
    genuinely large, active coins."""
    service = ScoringService(db=None)
    coin = DummyCoin(liquidity_usd=5_000_000, volume_24h_usd=50_000)
    score = service._liquidity_score(coin)
    assert score is not None
    assert score > 0


# --- Confidence shrinkage tests ---

WEIGHTS = {
    "liquidity": 0.10,
    "trend": 0.15,
    "wallet": 0.20,
    "narrative": 0.25,
    "community": 0.20,
}


def test_zero_available_signals_shrinks_to_neutral_not_zero():
    """Real edge case exposed by making liquidity conditional: a coin
    with implausible/manipulated liquidity AND nothing else checked yet
    can now have zero confirmed signals at all. This should read as
    'completely unknown' (neutral 50), matching what the general formula
    produces at confidence=0 - not a confidently bad hard 0, which was an
    inconsistency in the original early-return path."""
    service = ScoringService(db=None)
    score, confidence = service._weighted_average_with_confidence({}, [], WEIGHTS)
    assert score == service.NEUTRAL_SCORE
    assert confidence == 0.0


def test_full_confidence_when_all_five_signals_present():
    service = ScoringService(db=None)
    components = {"liquidity": 100.0, "trend": 50.0, "wallet": 100.0, "narrative": 100.0, "community": 100.0}
    available = ["liquidity", "trend", "wallet", "narrative", "community"]
    score, confidence = service._weighted_average_with_confidence(components, available, WEIGHTS)
    assert confidence == 1.0
    # With full confidence, no shrinkage - score should equal the raw weighted average
    raw = sum(components[k] * WEIGHTS[k] for k in available) / sum(WEIGHTS[k] for k in available)
    assert abs(score - raw) < 0.01


def test_low_confidence_pulls_score_toward_neutral():
    service = ScoringService(db=None)
    # This is the exact scenario from the bug report: maxed liquidity + neutral
    # trend default, nothing else available yet.
    components = {"liquidity": 100.0, "trend": 50.0}
    available = ["liquidity", "trend"]
    score, confidence = service._weighted_average_with_confidence(components, available, WEIGHTS)

    raw_score = (100.0 * 0.10 + 50.0 * 0.15) / (0.10 + 0.15)  # = 70.0, the old buggy result
    assert raw_score == 70.0

    # Confidence should be (0.10+0.15)/(0.10+0.15+0.20+0.25+0.20) = 0.25/0.90
    assert abs(confidence - (0.25 / 0.90)) < 0.001
    # The shrunk score must land strictly between the raw score and neutral (50),
    # and must NOT still be able to cross the 70-point alert threshold on
    # liquidity+trend alone.
    assert 50.0 < score < 70.0
    assert score < 70.0


def test_single_signal_shrinks_heavily_toward_neutral():
    service = ScoringService(db=None)
    components = {"liquidity": 100.0}
    available = ["liquidity"]
    score, confidence = service._weighted_average_with_confidence(components, available, WEIGHTS)
    # Only 10% of the full weight pool is backed by data - should be pulled
    # most of the way to neutral even though the raw signal is maxed out.
    assert confidence < 0.15
    assert score < 60.0  # nowhere near the raw 100.0 it would've been without shrinkage


def test_zero_weights_returns_zero_score_and_zero_confidence():
    service = ScoringService(db=None)
    zero_weights = {k: 0.0 for k in WEIGHTS}
    score, confidence = service._weighted_average_with_confidence(
        {"liquidity": 100.0}, ["liquidity"], zero_weights
    )
    assert score == 0.0
    assert confidence == 0.0


def test_confidence_never_exceeds_one():
    service = ScoringService(db=None)
    # Even if available weight somehow summed higher than full_weight (shouldn't
    # happen in practice), confidence must be clamped to 1.0.
    weights = {"liquidity": 0.5}
    score, confidence = service._weighted_average_with_confidence(
        {"liquidity": 80.0}, ["liquidity"], weights
    )
    assert confidence == 1.0
    assert score == 80.0
