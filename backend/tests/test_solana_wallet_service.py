from unittest.mock import MagicMock

from app.services.solana_wallet_service import SolanaWalletIntelligenceService


def make_service():
    return SolanaWalletIntelligenceService(db=MagicMock())


def test_reputation_score_breakeven_is_neutral():
    service = make_service()
    score = service._reputation_score({"roi_pct": 0.0, "total_pnl_usd": 0.0})
    assert score == 50.0


def test_reputation_score_total_loss_is_zero():
    service = make_service()
    score = service._reputation_score({"roi_pct": -100.0, "total_pnl_usd": -500.0})
    assert score == 0.0


def test_reputation_score_strong_gain_is_high():
    service = make_service()
    score = service._reputation_score({"roi_pct": 100.0, "total_pnl_usd": 1000.0})
    assert score == 100.0


def test_reputation_score_huge_gain_clips_at_100():
    service = make_service()
    score = service._reputation_score({"roi_pct": 500.0, "total_pnl_usd": 5000.0})
    assert score == 100.0


def test_reputation_score_moderate_loss_is_below_neutral():
    service = make_service()
    score = service._reputation_score({"roi_pct": -50.0, "total_pnl_usd": -200.0})
    assert score == 25.0


def test_reputation_score_falls_back_to_pnl_sign_when_no_roi():
    service = make_service()
    winning = service._reputation_score({"roi_pct": None, "total_pnl_usd": 50.0})
    losing = service._reputation_score({"roi_pct": None, "total_pnl_usd": -50.0})
    assert winning == 65.0
    assert losing == 35.0
    assert winning > losing


def test_reputation_score_neutral_when_totally_missing():
    service = make_service()
    score = service._reputation_score({"roi_pct": None, "total_pnl_usd": None})
    assert score == 50.0
