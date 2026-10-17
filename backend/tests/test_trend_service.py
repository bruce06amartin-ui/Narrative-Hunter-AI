from dataclasses import dataclass
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.services.trend_service import TrendDetectionService


@dataclass
class FakeSnapshot:
    recorded_at: datetime
    price_usd: float
    volume_24h_usd: float


def make_service():
    return TrendDetectionService(db=MagicMock())


def test_insufficient_history_returns_none():
    service = make_service()
    now = datetime.utcnow()
    snapshots = [FakeSnapshot(now, 1.0, 1000.0)]
    assert service._compute_trend_score(snapshots) is None


def test_very_new_coin_with_multiple_snapshots_but_no_elapsed_time_returns_none():
    """Real-world case found via production data: a coin only ~4 minutes
    old technically has >=2 price_history snapshots (passing the basic
    length check), but none of them are old enough to populate even the
    shortest (15min) window. Without the deeper fix, this used to compute
    a fake 'neutral' trend_score of exactly 50.0 instead of correctly
    reporting that no real trend signal exists yet."""
    service = make_service()
    now = datetime.utcnow()
    snapshots = [
        FakeSnapshot(now - timedelta(minutes=4), 1.0, 1000.0),
        FakeSnapshot(now - timedelta(minutes=2), 1.01, 1010.0),
        FakeSnapshot(now, 1.02, 1020.0),
    ]
    assert service._compute_trend_score(snapshots) is None


def test_steady_uptrend_scores_above_neutral():
    service = make_service()
    now = datetime.utcnow()
    # Price has been climbing steadily for 4+ hours, still climbing at the same pace.
    snapshots = [
        FakeSnapshot(now - timedelta(hours=4), 1.0, 10_000.0),
        FakeSnapshot(now - timedelta(hours=1), 1.4, 14_000.0),
        FakeSnapshot(now - timedelta(minutes=15), 1.5, 15_000.0),
        FakeSnapshot(now, 1.55, 15_500.0),
    ]
    score = service._compute_trend_score(snapshots)
    assert score > 50.0


def test_decaying_pump_scores_lower_than_steady_uptrend():
    service = make_service()
    now = datetime.utcnow()

    steady = [
        FakeSnapshot(now - timedelta(hours=4), 1.0, 10_000.0),
        FakeSnapshot(now - timedelta(hours=1), 1.4, 14_000.0),
        FakeSnapshot(now - timedelta(minutes=15), 1.5, 15_000.0),
        FakeSnapshot(now, 1.6, 16_000.0),
    ]
    # Same 4h move, but flatlined in the last 15 minutes - classic decaying pump.
    decaying = [
        FakeSnapshot(now - timedelta(hours=4), 1.0, 10_000.0),
        FakeSnapshot(now - timedelta(hours=1), 1.4, 14_000.0),
        FakeSnapshot(now - timedelta(minutes=15), 1.6, 16_000.0),
        FakeSnapshot(now, 1.6, 16_000.0),
    ]

    steady_score = service._compute_trend_score(steady)
    decaying_score = service._compute_trend_score(decaying)
    assert steady_score > decaying_score


def test_downtrend_scores_below_neutral():
    service = make_service()
    now = datetime.utcnow()
    snapshots = [
        FakeSnapshot(now - timedelta(hours=4), 2.0, 20_000.0),
        FakeSnapshot(now - timedelta(hours=1), 1.5, 15_000.0),
        FakeSnapshot(now - timedelta(minutes=15), 1.2, 12_000.0),
        FakeSnapshot(now, 1.0, 10_000.0),
    ]
    score = service._compute_trend_score(snapshots)
    assert score < 50.0


def test_decay_zero_when_long_rate_not_positive():
    service = make_service()
    assert service._decay({"long": -5.0, "short": -10.0}) == 0.0
    assert service._decay({"long": None, "short": 1.0}) == 0.0


def test_decay_full_when_short_rate_negative_after_positive_long():
    service = make_service()
    decay = service._decay({"long": 10.0, "short": -5.0})
    assert decay == 1.0


def test_acceleration_prefers_short_medium_pair():
    service = make_service()
    accel = service._acceleration({"short": 20.0, "medium": 10.0, "long": 5.0})
    assert accel == 10.0


def test_momentum_score_bounded():
    service = make_service()
    extreme = service._momentum_score(velocity=10_000, acceleration=10_000, decay=0.0, volume_confirmation=10_000)
    assert 0.0 <= extreme <= 100.0
