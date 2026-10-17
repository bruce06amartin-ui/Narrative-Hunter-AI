from unittest.mock import patch

from app.collectors.rugcheck import RugCheckCollector

SAMPLE_RESPONSE = {
    "score_normalised": 65.0,
    "risks": [
        {"name": "Low liquidity"},
        "Mint authority active",
    ],
}


def make_collector():
    return RugCheckCollector()


def test_get_risk_summary_parses_correctly():
    collector = make_collector()
    with patch("app.collectors.rugcheck.get_json", return_value=SAMPLE_RESPONSE):
        result = collector.get_risk_summary("SomeMintAddress")

    assert result is not None
    assert result["risk_score"] == 65.0
    assert result["risks"] == ["Low liquidity", "Mint authority active"]


def test_get_risk_summary_returns_none_when_score_normalised_missing():
    collector = make_collector()
    ambiguous_response = {"trustScore": 90, "score": 1200}
    with patch("app.collectors.rugcheck.get_json", return_value=ambiguous_response):
        result = collector.get_risk_summary("SomeMintAddress")

    assert result is None


def test_get_risk_summary_clips_to_0_100_range():
    collector = make_collector()
    with patch("app.collectors.rugcheck.get_json", return_value={"score_normalised": 150}):
        result = collector.get_risk_summary("SomeMintAddress")
    assert result["risk_score"] == 100.0

    with patch("app.collectors.rugcheck.get_json", return_value={"score_normalised": -10}):
        result = collector.get_risk_summary("SomeMintAddress")
    assert result["risk_score"] == 0.0


def test_get_risk_summary_handles_non_numeric_score():
    collector = make_collector()
    with patch("app.collectors.rugcheck.get_json", return_value={"score_normalised": "not-a-number"}):
        result = collector.get_risk_summary("SomeMintAddress")
    assert result is None


def test_get_risk_summary_handles_api_failure():
    from app.collectors.base import CollectorHTTPError
    collector = make_collector()
    with patch("app.collectors.rugcheck.get_json", side_effect=CollectorHTTPError("boom")):
        result = collector.get_risk_summary("SomeMintAddress")
    assert result is None


def test_get_risk_summary_handles_missing_risks_field_gracefully():
    collector = make_collector()
    with patch("app.collectors.rugcheck.get_json", return_value={"score_normalised": 20.0}):
        result = collector.get_risk_summary("SomeMintAddress")
    assert result == {"risk_score": 20.0, "risks": []}


def test_headers_includes_key_when_configured():
    collector = make_collector()
    with patch("app.collectors.rugcheck.settings.rugcheck_api_key", "fake-key"):
        assert collector._headers() == {"X-API-KEY": "fake-key"}


def test_headers_empty_when_not_configured():
    collector = make_collector()
    with patch("app.collectors.rugcheck.settings.rugcheck_api_key", None):
        assert collector._headers() == {}
