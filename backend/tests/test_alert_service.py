from dataclasses import dataclass
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.alert_service import AlertService


@dataclass
class FakeHistoricalScore:
    overall_score: float
    risk_score: float | None
    recorded_at: datetime


class FakeCoin:
    id = "coin-1"
    liquidity_usd = 50_000.0  # well above the default alert_min_liquidity_usd gate


def make_service(existing_alert=None):
    """Builds an AlertService with a mocked db whose query().filter().first()
    returns `existing_alert` (None = no prior alert, dedup won't block)."""
    service = AlertService(db=MagicMock())
    query_mock = service.db.query.return_value
    filter_mock = query_mock.filter.return_value
    filter_mock.first.return_value = existing_alert
    return service


def test_overall_score_crossing_triggers_alert():
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=60.0, risk_score=None, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=75.0, risk_score=None, recorded_at=datetime.utcnow())

    alert = service._check_overall_score_threshold(FakeCoin(), current, previous)

    assert alert is not None
    assert alert.alert_type == "overall_score_threshold"
    assert alert.trigger_value == 75.0


def test_overall_score_no_crossing_when_already_above():
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=80.0, risk_score=None, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=82.0, risk_score=None, recorded_at=datetime.utcnow())

    alert = service._check_overall_score_threshold(FakeCoin(), current, previous)

    assert alert is None  # was already above threshold, not a fresh crossing


def test_overall_score_dedup_blocks_repeat_alert():
    # Simulate: an alert was already created for this exact data point
    service = make_service(existing_alert=MagicMock())
    previous = FakeHistoricalScore(overall_score=60.0, risk_score=None, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=75.0, risk_score=None, recorded_at=datetime.utcnow())

    alert = service._check_overall_score_threshold(FakeCoin(), current, previous)

    assert alert is None  # dedup should suppress it


def test_risk_score_change_triggers_alert():
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=50.0, risk_score=20.0, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=50.0, risk_score=55.0, recorded_at=datetime.utcnow())

    with patch("app.services.alert_service.settings.alert_positive_only", False):
        alert = service._check_risk_score_change(FakeCoin(), current, previous)

    assert alert is not None
    assert alert.alert_type == "risk_score_change"
    assert "increased" in alert.message


def test_risk_score_change_below_threshold_no_alert():
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=50.0, risk_score=20.0, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=50.0, risk_score=25.0, recorded_at=datetime.utcnow())

    with patch("app.services.alert_service.settings.alert_positive_only", False):
        alert = service._check_risk_score_change(FakeCoin(), current, previous)

    assert alert is None


def test_risk_score_change_missing_data_no_alert():
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=50.0, risk_score=None, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=50.0, risk_score=55.0, recorded_at=datetime.utcnow())

    with patch("app.services.alert_service.settings.alert_positive_only", False):
        alert = service._check_risk_score_change(FakeCoin(), current, previous)

    assert alert is None


def test_risk_score_decrease_also_triggers_and_is_not_critical():
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=50.0, risk_score=80.0, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=50.0, risk_score=40.0, recorded_at=datetime.utcnow())

    alert = service._check_risk_score_change(FakeCoin(), current, previous)

    assert alert is not None
    assert "decreased" in alert.message
    assert alert.severity == "warning"


class FakeCoinForTradeUrl:
    def __init__(self, chain, pair_address):
        self.chain = chain
        self.pair_address = pair_address


def test_build_trade_url_solana():
    service = AlertService(db=MagicMock())
    coin = FakeCoinForTradeUrl(chain="solana", pair_address="ABC123pool")
    url = service._build_trade_url(coin)
    assert url == "https://www.geckoterminal.com/solana/pools/ABC123pool"


def test_build_trade_url_eth_no_translation_needed():
    """Unlike the earlier DexScreener version, GeckoTerminal's website slug
    for Ethereum is literally 'eth' - the same value already stored in
    Coin.chain - verified against real, currently-indexed GeckoTerminal
    pages, not just documentation."""
    service = AlertService(db=MagicMock())
    coin = FakeCoinForTradeUrl(chain="eth", pair_address="0xdeadbeef")
    url = service._build_trade_url(coin)
    assert url == "https://www.geckoterminal.com/eth/pools/0xdeadbeef"


def test_build_trade_url_base():
    service = AlertService(db=MagicMock())
    coin = FakeCoinForTradeUrl(chain="base", pair_address="0xcafebabe")
    url = service._build_trade_url(coin)
    assert url == "https://www.geckoterminal.com/base/pools/0xcafebabe"


def test_build_trade_url_none_when_no_pair_address():
    service = AlertService(db=MagicMock())
    coin = FakeCoinForTradeUrl(chain="solana", pair_address=None)
    url = service._build_trade_url(coin)
    assert url is None


def test_overall_score_alert_blocked_by_high_risk_score():
    """Real issue found via user data: ~27% of alerts turned out to be
    already-rugged coins, because the risk penalty in overall_score is
    proportional, not a hard cutoff - a coin could cross 70 on strong
    other signals despite a genuinely high risk_score."""
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=60.0, risk_score=65.0, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=75.0, risk_score=65.0, recorded_at=datetime.utcnow())

    alert = service._check_overall_score_threshold(FakeCoin(), current, previous)

    assert alert is None  # crossed 70, but risk_score (65) is above the 60 gate


def test_overall_score_alert_allowed_when_risk_score_is_null():
    """A risk_score that simply hasn't been checked yet must NOT block the
    alert - only a CONFIRMED high risk_score should."""
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=60.0, risk_score=None, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=75.0, risk_score=None, recorded_at=datetime.utcnow())

    alert = service._check_overall_score_threshold(FakeCoin(), current, previous)

    assert alert is not None


def test_overall_score_alert_allowed_when_risk_score_below_gate():
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=60.0, risk_score=20.0, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=75.0, risk_score=20.0, recorded_at=datetime.utcnow())

    alert = service._check_overall_score_threshold(FakeCoin(), current, previous)

    assert alert is not None


def test_overall_score_alert_blocked_at_exact_gate_boundary():
    """risk_score exactly AT the gate (60) should block, matching '>= gate'
    semantics - consistent with the paper trading gate's own boundary."""
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=60.0, risk_score=60.0, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=75.0, risk_score=60.0, recorded_at=datetime.utcnow())

    alert = service._check_overall_score_threshold(FakeCoin(), current, previous)

    assert alert is None


class FakeCoinWithLiquidity:
    id = "coin-1"

    def __init__(self, liquidity_usd):
        self.liquidity_usd = liquidity_usd


def test_overall_score_alert_blocked_by_low_liquidity():
    """Real user feedback: alerts were firing for coins with negligible
    liquidity that crossed the score threshold on other signals alone -
    not meaningful opportunities regardless of their per-token price."""
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=60.0, risk_score=None, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=75.0, risk_score=None, recorded_at=datetime.utcnow())

    alert = service._check_overall_score_threshold(FakeCoinWithLiquidity(liquidity_usd=500.0), current, previous)

    assert alert is None  # crossed 70, but liquidity ($500) is well under the $10,000 gate


def test_overall_score_alert_allowed_above_liquidity_gate():
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=60.0, risk_score=None, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=75.0, risk_score=None, recorded_at=datetime.utcnow())

    alert = service._check_overall_score_threshold(FakeCoinWithLiquidity(liquidity_usd=50_000.0), current, previous)

    assert alert is not None


def test_overall_score_alert_blocked_when_liquidity_is_none():
    """Unlike risk_score, a missing liquidity value does NOT get the
    benefit of the doubt - liquidity is essentially always known by the
    time a coin has a score, so null is treated as zero."""
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=60.0, risk_score=None, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=75.0, risk_score=None, recorded_at=datetime.utcnow())

    alert = service._check_overall_score_threshold(FakeCoinWithLiquidity(liquidity_usd=None), current, previous)

    assert alert is None


def test_risk_score_change_blocked_by_low_liquidity():
    """This was the actual gap causing the reported problem: real user
    data showed 20 consecutive risk_score_change alerts, many for
    negligible-liquidity coins - this alert type never had the liquidity
    gate the other three alert types already had."""
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=50.0, risk_score=20.0, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=50.0, risk_score=55.0, recorded_at=datetime.utcnow())

    coin = FakeCoinWithLiquidity(liquidity_usd=200.0)
    alert = service._check_risk_score_change(coin, current, previous)

    assert alert is None  # risk jumped 35 points, but liquidity ($200) is well under the gate


def test_risk_score_change_allowed_above_liquidity_gate():
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=50.0, risk_score=20.0, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=50.0, risk_score=55.0, recorded_at=datetime.utcnow())

    coin = FakeCoinWithLiquidity(liquidity_usd=50_000.0)
    alert = service._check_risk_score_change(coin, current, previous)

    assert alert is not None


def test_positive_only_mode_blocks_risk_increase():
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=50.0, risk_score=20.0, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=50.0, risk_score=55.0, recorded_at=datetime.utcnow())

    with patch("app.services.alert_service.settings.alert_positive_only", True):
        alert = service._check_risk_score_change(FakeCoin(), current, previous)

    assert alert is None  # risk increased - suppressed in positive-only mode


def test_positive_only_mode_allows_risk_decrease():
    """A risk DECREASE is still good news (e.g. liquidity just got locked)
    and should come through even in positive-only mode."""
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=50.0, risk_score=80.0, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=50.0, risk_score=40.0, recorded_at=datetime.utcnow())

    with patch("app.services.alert_service.settings.alert_positive_only", True):
        alert = service._check_risk_score_change(FakeCoin(), current, previous)

    assert alert is not None
    assert "decreased" in alert.message


def test_positive_only_mode_disabled_allows_risk_increase():
    service = make_service(existing_alert=None)
    previous = FakeHistoricalScore(overall_score=50.0, risk_score=20.0, recorded_at=datetime.utcnow() - timedelta(minutes=5))
    current = FakeHistoricalScore(overall_score=50.0, risk_score=55.0, recorded_at=datetime.utcnow())

    with patch("app.services.alert_service.settings.alert_positive_only", False):
        alert = service._check_risk_score_change(FakeCoin(), current, previous)

    assert alert is not None


def test_cleanup_old_alerts_uses_configured_default_retention():
    service = AlertService(db=MagicMock())
    service.db.query.return_value.filter.return_value.delete.return_value = 7

    with patch("app.services.alert_service.settings.alert_retention_days", 30):
        result = service.cleanup_old_alerts()

    assert result["deleted"] == 7
    assert result["retention_days"] == 30
    service.db.commit.assert_called_once()


def test_cleanup_old_alerts_respects_explicit_override():
    """Passing a specific retention_days should use that instead of the
    configured default - lets a manual test run with a shorter window
    without changing global settings."""
    service = AlertService(db=MagicMock())
    service.db.query.return_value.filter.return_value.delete.return_value = 3

    with patch("app.services.alert_service.settings.alert_retention_days", 30):
        result = service.cleanup_old_alerts(retention_days=7)

    assert result["deleted"] == 3
    assert result["retention_days"] == 7


def test_cleanup_old_alerts_returns_zero_when_nothing_to_delete():
    service = AlertService(db=MagicMock())
    service.db.query.return_value.filter.return_value.delete.return_value = 0

    result = service.cleanup_old_alerts(retention_days=30)

    assert result["deleted"] == 0


class FakeCoinManipulatedLiquidity:
    """The exact real-world case that prompted this fix: a coin
    reporting $269M liquidity but only $1.10 in 24h volume."""
    id = "coin-manipulated"
    liquidity_usd = 269_100_000.0
    volume_24h_usd = 1.10


class FakeCoinLegitimateHighLiquidity:
    liquidity_usd = 5_000_000.0
    volume_24h_usd = 50_000.0  # a realistic ~1% daily volume ratio


class FakeCoinBelowMinimum:
    liquidity_usd = 500.0
    volume_24h_usd = None


def test_liquidity_gate_rejects_real_manipulated_case():
    service = make_service()
    assert service._passes_liquidity_gate(FakeCoinManipulatedLiquidity()) is False


def test_liquidity_gate_accepts_legitimate_high_liquidity_coin():
    service = make_service()
    assert service._passes_liquidity_gate(FakeCoinLegitimateHighLiquidity()) is True


def test_liquidity_gate_rejects_below_minimum_threshold():
    service = make_service()
    assert service._passes_liquidity_gate(FakeCoinBelowMinimum()) is False


class FakeCoinNormalAboveMinimum:
    liquidity_usd = 50_000.0  # above the $10k minimum, below the $1M manipulation-check threshold
    volume_24h_usd = 100.0


def test_liquidity_gate_accepts_normal_coin_above_minimum():
    service = make_service()
    assert service._passes_liquidity_gate(FakeCoinNormalAboveMinimum()) is True


class FakeCoinLegitimateButDead:
    """Real, non-manipulated liquidity (well below the $1M manipulation
    threshold, so it would have passed every existing check), but
    genuinely near-zero volume - the exact real-world case that prompted
    this fix: a small pump.fun coin whose real trading has simply
    stopped, not a fake-liquidity scam."""
    liquidity_usd = 15_000.0
    volume_24h_usd = 5.0


class FakeCoinUnknownVolume:
    liquidity_usd = 20_000.0
    volume_24h_usd = None


def test_liquidity_gate_rejects_legitimate_but_dead_coin():
    """The actual real-world case: this coin would have PASSED every
    check before this fix (real liquidity above the minimum, and nowhere
    near large enough to trigger the manipulation check), but its
    near-zero volume means it's genuinely no longer being traded."""
    service = make_service()
    assert service._passes_liquidity_gate(FakeCoinLegitimateButDead()) is False


def test_liquidity_gate_gives_benefit_of_doubt_for_unknown_volume():
    """Missing volume data shouldn't be treated as 'dead' - consistent
    with how the manipulation check already handles missing data."""
    service = make_service()
    assert service._passes_liquidity_gate(FakeCoinUnknownVolume()) is True


class FakeCoinForWhaleEntry:
    """Real production case: $67,208 liquidity."""
    id = "coin-fwadate"
    chain = "eth"
    liquidity_usd = 67208.21
    contract_address = "0x847e4add197a5ae69db809bc1486f2772e81c5fa"


class FakeWalletTx:
    def __init__(self, amount, block_timestamp):
        self.amount = amount
        self.block_timestamp = block_timestamp


def test_whale_entry_skips_implausible_estimate_exceeding_liquidity():
    """The exact real-world case: a coin with $67,208 liquidity showed a
    'whale' alert claiming a single $228,300 purchase - over 3x the
    entire pool. Both candidate transactions here are implausible
    (exceed liquidity), so the function should find nothing and return
    None, rather than alerting on either one."""
    from unittest.mock import patch
    from datetime import datetime, timezone

    service = make_service()
    coin = FakeCoinForWhaleEntry()

    implausible_tx = FakeWalletTx(amount=1_000_000_000, block_timestamp=datetime.now(timezone.utc))
    also_implausible_tx = FakeWalletTx(amount=500_000_000, block_timestamp=datetime.now(timezone.utc))

    service.db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        implausible_tx, also_implausible_tx
    ]

    # price such that amount * price >= liquidity_usd for both candidates
    # (1,000,000,000 * 0.0002283 = 228,300 - the real FWADATE case)
    with patch.object(service, "_nearest_price_usd", return_value=0.0002283):
        result = service._check_whale_entry(coin)

    assert result is None


def test_whale_entry_allows_plausible_estimate_below_liquidity():
    """A genuinely plausible transaction (above the real $10,000 alert
    threshold, but well below the pool's own liquidity) should NOT be
    filtered out by the sanity check, and should produce a real alert."""
    from unittest.mock import patch
    from datetime import datetime, timezone

    service = make_service()
    coin = FakeCoinForWhaleEntry()

    plausible_tx = FakeWalletTx(amount=1000, block_timestamp=datetime.now(timezone.utc))
    service.db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        plausible_tx
    ]
    # Same shared filter mock also serves the dedup query
    # (self.db.query(Alert).filter(...).first()) - explicitly return None
    # so it doesn't look like a duplicate already exists.
    service.db.query.return_value.filter.return_value.first.return_value = None

    # 1000 * 15.0 = $15,000 - above the real $10,000 threshold, well
    # below the $67,208.21 liquidity ceiling.
    with patch.object(service, "_nearest_price_usd", return_value=15.0), \
         patch.object(service, "_passes_liquidity_gate", return_value=True):
        result = service._check_whale_entry(coin)

    assert result is not None
    assert result.trigger_value == 15000.0
