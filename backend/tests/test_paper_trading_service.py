from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.paper_trading_service import PaperTradingService


def make_service():
    return PaperTradingService(db=MagicMock())


def make_coin(price_usd=0.001, symbol="TEST", chain="base"):
    return SimpleNamespace(id="coin-1", price_usd=price_usd, symbol=symbol, chain=chain, name="Test Coin")


def make_history(overall_score, risk_score=None):
    return SimpleNamespace(overall_score=overall_score, risk_score=risk_score)


def setup_query_chain(db_mock, existing_open_trade, history_rows):
    call_count = {"n": 0}

    def query_side_effect(*args, **kwargs):
        call_count["n"] += 1
        mock_query = MagicMock()
        if call_count["n"] == 1:
            mock_query.filter.return_value.first.return_value = existing_open_trade
        else:
            mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = history_rows
        return mock_query

    db_mock.query.side_effect = query_side_effect


def test_enters_trade_on_valid_crossing_with_risk_gate_passed():
    service = make_service()
    coin = make_coin(price_usd=0.001)
    history = [make_history(overall_score=72.0, risk_score=30.0), make_history(overall_score=65.0, risk_score=25.0)]
    setup_query_chain(service.db, existing_open_trade=None, history_rows=history)

    result = service._maybe_enter(coin)

    assert result is True
    service.db.add.assert_called_once()
    added_trade = service.db.add.call_args[0][0]
    assert added_trade.entry_price_usd == 0.001
    assert added_trade.entry_overall_score == 72.0
    assert added_trade.entry_risk_score == 30.0


def test_skips_entry_when_risk_gate_fails():
    service = make_service()
    coin = make_coin()
    history = [make_history(overall_score=75.0, risk_score=65.0), make_history(overall_score=65.0, risk_score=60.0)]
    setup_query_chain(service.db, existing_open_trade=None, history_rows=history)

    result = service._maybe_enter(coin)

    assert result is False
    service.db.add.assert_not_called()


def test_allows_entry_when_risk_score_is_unavailable():
    service = make_service()
    coin = make_coin()
    history = [make_history(overall_score=75.0, risk_score=None), make_history(overall_score=65.0, risk_score=None)]
    setup_query_chain(service.db, existing_open_trade=None, history_rows=history)

    result = service._maybe_enter(coin)

    assert result is True


def test_skips_entry_when_no_crossing_occurred():
    service = make_service()
    coin = make_coin()
    history = [make_history(overall_score=75.0, risk_score=10.0), make_history(overall_score=74.0, risk_score=10.0)]
    setup_query_chain(service.db, existing_open_trade=None, history_rows=history)

    result = service._maybe_enter(coin)

    assert result is False
    service.db.add.assert_not_called()


def test_skips_entry_when_position_already_open():
    service = make_service()
    coin = make_coin()
    existing_trade = SimpleNamespace(id="existing-trade")
    setup_query_chain(service.db, existing_open_trade=existing_trade, history_rows=[])

    result = service._maybe_enter(coin)

    assert result is False
    service.db.add.assert_not_called()


def test_skips_entry_with_insufficient_history():
    service = make_service()
    coin = make_coin()
    history = [make_history(overall_score=75.0, risk_score=10.0)]
    setup_query_chain(service.db, existing_open_trade=None, history_rows=history)

    result = service._maybe_enter(coin)

    assert result is False


def test_exit_closes_and_computes_correct_pnl():
    service = make_service()
    open_trade = SimpleNamespace(
        entry_price_usd=0.001, position_size_gbp=50.0, status="open",
        exit_price_usd=None, exit_at=None, pnl_gbp=None, pnl_pct=None, exit_reason=None,
        symbol="TEST", chain="base", entry_at=datetime.utcnow() - timedelta(hours=1),
    )
    service.db.query.return_value.filter.return_value.first.return_value = open_trade

    coin = make_coin(price_usd=0.0015)  # +50%, matches the current exit_gain_pct default

    result = service._maybe_exit(coin)

    assert result is True
    assert open_trade.status == "closed"
    assert open_trade.exit_reason == "take_profit"
    assert abs(open_trade.pnl_pct - 50.0) < 0.001
    assert abs(open_trade.pnl_gbp - 25.00) < 0.001


def test_exit_stays_open_below_target():
    service = make_service()
    open_trade = SimpleNamespace(
        entry_price_usd=0.001, position_size_gbp=50.0, status="open",
        exit_price_usd=None, exit_at=None, pnl_gbp=None, pnl_pct=None, exit_reason=None,
        symbol="TEST", chain="base", entry_at=datetime.utcnow() - timedelta(hours=1),
    )
    service.db.query.return_value.filter.return_value.first.return_value = open_trade

    coin = make_coin(price_usd=0.0011)

    result = service._maybe_exit(coin)

    assert result is False
    assert open_trade.status == "open"


def test_exit_computes_larger_gain_correctly():
    service = make_service()
    open_trade = SimpleNamespace(
        entry_price_usd=0.001, position_size_gbp=50.0, status="open",
        exit_price_usd=None, exit_at=None, pnl_gbp=None, pnl_pct=None, exit_reason=None,
        symbol="TEST", chain="base", entry_at=datetime.utcnow() - timedelta(hours=1),
    )
    service.db.query.return_value.filter.return_value.first.return_value = open_trade

    coin = make_coin(price_usd=0.002)

    result = service._maybe_exit(coin)

    assert result is True
    assert abs(open_trade.pnl_pct - 100.0) < 0.001
    assert abs(open_trade.pnl_gbp - 50.0) < 0.001


def test_exit_closes_on_stop_loss():
    """The core real gap this fix closes: before this, a losing position
    had NO way to ever close, meaning win_rate_pct was structurally
    guaranteed to trend toward 100% (every closeable trade was, by
    definition, a win). This confirms a genuine loss now closes and
    records a real negative pnl."""
    service = make_service()
    open_trade = SimpleNamespace(
        entry_price_usd=0.001, position_size_gbp=50.0, status="open",
        exit_price_usd=None, exit_at=None, pnl_gbp=None, pnl_pct=None, exit_reason=None,
        symbol="TEST", chain="base", entry_at=datetime.utcnow() - timedelta(hours=1),
    )
    service.db.query.return_value.filter.return_value.first.return_value = open_trade

    # 0.0005 = -50% from 0.001 entry, exactly at the current stop-loss threshold
    coin = make_coin(price_usd=0.0005)

    result = service._maybe_exit(coin)

    assert result is True
    assert open_trade.status == "closed"
    assert open_trade.exit_reason == "stop_loss"
    assert abs(open_trade.pnl_pct - (-50.0)) < 0.001
    assert abs(open_trade.pnl_gbp - (-25.0)) < 0.001


def test_exit_closes_on_max_hold_timeout_even_when_flat():
    """The other real gap this fix closes: a position that never hits
    either take-profit or stop-loss - just sits flat or mildly negative
    forever - previously stayed open indefinitely. This confirms it now
    force-closes after the configured hold window, with whatever the
    real price happens to be at that time."""
    service = make_service()
    open_trade = SimpleNamespace(
        entry_price_usd=0.001, position_size_gbp=50.0, status="open",
        exit_price_usd=None, exit_at=None, pnl_gbp=None, pnl_pct=None, exit_reason=None,
        symbol="TEST", chain="base", entry_at=datetime.utcnow() - timedelta(hours=100),
    )
    service.db.query.return_value.filter.return_value.first.return_value = open_trade

    # Only +2% - nowhere near take-profit (25%) or stop-loss (-20%),
    # but entry_at is 100h ago, past the 72h max_hold_hours default.
    coin = make_coin(price_usd=0.00102)

    result = service._maybe_exit(coin)

    assert result is True
    assert open_trade.status == "closed"
    assert open_trade.exit_reason == "max_hold_timeout"
    assert abs(open_trade.pnl_pct - 2.0) < 0.001


def test_exit_stays_open_when_within_all_thresholds_and_hold_window():
    """A position that's genuinely still fine on every dimension - not
    yet at target, not at stop-loss, not timed out - should correctly
    remain open. Confirms the fix didn't make the system over-eager to
    close positions."""
    service = make_service()
    open_trade = SimpleNamespace(
        entry_price_usd=0.001, position_size_gbp=50.0, status="open",
        exit_price_usd=None, exit_at=None, pnl_gbp=None, pnl_pct=None, exit_reason=None,
        symbol="TEST", chain="base", entry_at=datetime.utcnow() - timedelta(hours=1),
    )
    service.db.query.return_value.filter.return_value.first.return_value = open_trade

    coin = make_coin(price_usd=0.00095)  # -5%, above stop-loss, well within hold window

    result = service._maybe_exit(coin)

    assert result is False
    assert open_trade.status == "open"
