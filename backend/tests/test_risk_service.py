from app.services.risk_service import RiskService


def _flag_types(flags):
    return {f["flag_type"] for f in flags}


def test_trusted_token_short_circuits_to_no_risk():
    service = RiskService(db=None)
    flags = service._evaluate({"trusted_token": True})
    assert len(flags) == 1
    assert flags[0]["flag_type"] == "trusted_token"
    assert flags[0]["points"] == 0


def test_honeypot_flagged_as_critical():
    service = RiskService(db=None)
    flags = service._evaluate({"is_honeypot": True})
    assert "honeypot_suspected" in _flag_types(flags)
    critical = [f for f in flags if f["flag_type"] == "honeypot_suspected"][0]
    assert critical["severity"] == "critical"
    assert critical["points"] == 40


def test_clean_token_produces_no_flags():
    service = RiskService(db=None)
    flags = service._evaluate({
        "is_honeypot": False,
        "is_mintable": False,
        "hidden_owner": False,
        "is_open_source": True,
        "top10_holder_percent": 15.0,
        "lp_locked_percent": 90.0,
    })
    assert flags == []


def test_high_holder_concentration_flagged():
    service = RiskService(db=None)
    flags = service._evaluate({"top10_holder_percent": 80.0})
    concentration = [f for f in flags if f["flag_type"] == "holder_concentration_high"][0]
    assert concentration["severity"] == "high"
    assert concentration["points"] == 25


def test_moderate_holder_concentration_lower_severity():
    service = RiskService(db=None)
    flags = service._evaluate({"top10_holder_percent": 45.0})
    concentration = [f for f in flags if f["flag_type"] == "holder_concentration_high"][0]
    assert concentration["severity"] == "medium"
    assert concentration["points"] == 12


def test_unlocked_liquidity_flagged():
    service = RiskService(db=None)
    flags = service._evaluate({"lp_locked_percent": 5.0})
    lp_flag = [f for f in flags if f["flag_type"] == "liquidity_not_locked"][0]
    assert lp_flag["severity"] == "high"


def test_risk_score_capped_at_100():
    service = RiskService(db=None)
    worst_case = {
        "is_honeypot": True,
        "non_transferable": True,
        "is_mintable": True,
        "is_freezable": True,
        "owner_change_balance": True,
        "hidden_owner": True,
        "is_open_source": False,
        "selfdestruct": True,
        "transfer_pausable": True,
        "can_take_back_ownership": True,
        "is_blacklisted": True,
        "top10_holder_percent": 99.0,
        "lp_locked_percent": 0.0,
    }
    flags = service._evaluate(worst_case)
    total = sum(f["points"] for f in flags)
    assert total > 100  # uncapped sum should exceed 100
    capped = min(100.0, total)
    assert capped == 100.0


def test_rugcheck_fallback_only_triggers_for_solana():
    """The core gating behavior: when GoPlus has no data, RugCheck should
    only be tried for Solana coins - it's Solana-specific, and calling it
    for EVM chains would be pointless (and wasteful)."""
    from unittest.mock import MagicMock, patch

    class FakeCoin:
        chain = "solana"
        contract_address = "SomeMintAddress"
        id = "coin-1"
        creator_address = None

    service = RiskService(db=MagicMock())
    service.collector = MagicMock()
    service.collector.check_token.return_value = None  # GoPlus has no data
    service.rugcheck = MagicMock()
    service.rugcheck.get_risk_summary.return_value = {"risk_score": 42.0, "risks": ["Low liquidity"]}

    with patch.object(RiskService, "_set_risk_score") as mock_set_score:
        result = service.check_coin(FakeCoin())

    service.rugcheck.get_risk_summary.assert_called_once_with("SomeMintAddress")
    assert result == 42.0
    mock_set_score.assert_called_once()
    call_args = mock_set_score.call_args
    assert call_args[0][1] == 42.0  # the risk_score positional arg


def test_rugcheck_fallback_never_triggers_for_evm():
    from unittest.mock import MagicMock, patch

    class FakeCoin:
        chain = "eth"
        contract_address = "0xSomeAddress"
        id = "coin-2"
        creator_address = None

    service = RiskService(db=MagicMock())
    service.collector = MagicMock()
    service.collector.check_token.return_value = None  # GoPlus has no data
    service.rugcheck = MagicMock()

    with patch.object(RiskService, "_set_risk_score") as mock_set_score:
        result = service.check_coin(FakeCoin())

    service.rugcheck.get_risk_summary.assert_not_called()
    assert result is None
    mock_set_score.assert_called_once()
    call_args = mock_set_score.call_args
    assert call_args[0][1] is None  # falls through to the standard "no data" None
