from unittest.mock import MagicMock

from app.services.wallet_service import WalletIntelligenceService


def make_service():
    return WalletIntelligenceService(db=MagicMock())


def test_reputation_no_roi_data_capped_low():
    service = make_service()
    score = service._reputation_score(win_rate=None, avg_roi=None, early_freq=1.0, total_positions=5)
    assert score <= 50.0


def test_reputation_perfect_track_record_high():
    service = make_service()
    score = service._reputation_score(win_rate=1.0, avg_roi=100.0, early_freq=1.0, total_positions=10)
    assert score > 80.0


def test_reputation_poor_track_record_low():
    service = make_service()
    score = service._reputation_score(win_rate=0.0, avg_roi=-40.0, early_freq=0.0, total_positions=10)
    assert score < 15.0


def test_reputation_low_sample_size_penalized_via_confidence():
    service = make_service()
    high_sample = service._reputation_score(win_rate=0.6, avg_roi=20.0, early_freq=0.5, total_positions=10)
    low_sample = service._reputation_score(win_rate=0.6, avg_roi=20.0, early_freq=0.5, total_positions=1)
    assert high_sample > low_sample


def test_reputation_bounded_0_to_100():
    service = make_service()
    extreme_high = service._reputation_score(win_rate=1.0, avg_roi=10000.0, early_freq=1.0, total_positions=100)
    extreme_low = service._reputation_score(win_rate=0.0, avg_roi=-10000.0, early_freq=0.0, total_positions=100)
    assert 0.0 <= extreme_low <= extreme_high <= 100.0


def test_count_strong_holding_wallets_handles_timezone_aware_timestamps():
    """Real production bug found via live logs: block_timestamp is stored
    as DateTime(timezone=True), so rows fetched from the DB come back
    timezone-aware. The old code computed cutoff via datetime.utcnow()
    (timezone-naive), and compared it directly against r.first_in in a
    plain Python list comprehension (not a SQL filter, so Postgres never
    got a chance to handle the conversion) - raising
    'can't compare offset-naive and offset-aware datetimes' on every
    single coin checked, silently making the whole alert cycle take far
    longer than it should. This confirms the fix runs without raising -
    using timestamps old enough that recent_holder_ids ends up empty,
    cleanly hitting the function's early-return path without needing to
    mock the separate downstream Wallet query."""
    from datetime import datetime, timedelta, timezone
    from dataclasses import dataclass

    @dataclass
    class FakeRow:
        wallet_id: str
        net: float
        first_in: datetime

    service = make_service()
    long_ago = datetime.now(timezone.utc) - timedelta(days=365)
    fake_rows = [FakeRow(wallet_id="wallet-ancient", net=100.0, first_in=long_ago)]
    service.db.query.return_value.filter.return_value.group_by.return_value.having.return_value.all.return_value = fake_rows

    # The actual regression test: this line used to raise
    # "can't compare offset-naive and offset-aware datetimes"
    result = service.count_strong_holding_wallets(coin_id="some-coin-id")

    assert result == 0
