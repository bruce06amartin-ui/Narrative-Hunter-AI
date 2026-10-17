from app.services.narrative_ai_service import NarrativeAIService


def make_service():
    return NarrativeAIService()


def test_parse_json_response_plain():
    service = make_service()
    raw = '{"main_topic": "frog meme", "virality_score": 80}'
    parsed = service._parse_json_response(raw)
    assert parsed["main_topic"] == "frog meme"
    assert parsed["virality_score"] == 80


def test_parse_json_response_with_markdown_fence():
    service = make_service()
    raw = '```json\n{"main_topic": "dog meme"}\n```'
    parsed = service._parse_json_response(raw)
    assert parsed["main_topic"] == "dog meme"


def test_parse_json_response_invalid_returns_none():
    service = make_service()
    assert service._parse_json_response("not json at all") is None


def test_validate_clips_scores_and_coerces_types():
    service = make_service()
    result = service._validate(
        {
            "main_topic": "cats",
            "virality_score": 150,  # out of range, should clip to 100
            "narrative_score": -20,  # out of range, should clip to 0
            "is_funny": "yes",  # not a real bool, should become None
            "is_controversial": True,
            "related_events": None,
        }
    )
    assert result["virality_score"] == 100.0
    assert result["narrative_score"] == 0.0
    assert result["is_funny"] is None
    assert result["is_controversial"] is True
    assert result["related_events"] is None


def test_validate_handles_missing_fields_gracefully():
    service = make_service()
    result = service._validate({})
    assert result["main_topic"] is None
    assert result["virality_score"] is None
    assert result["is_funny"] is None


def test_analyze_returns_none_when_not_configured():
    service = make_service()
    # No ANTHROPIC_API_KEY set by default in test env
    from app.config import settings

    settings.anthropic_api_key = None
    assert service.analyze("TEST (Test Coin)", [{"source": "reddit", "text": "hi", "engagement_score": 1}]) is None


def test_analyze_returns_none_with_no_posts():
    service = make_service()
    from app.config import settings

    settings.anthropic_api_key = "fake-key-for-test"
    assert service.analyze("TEST (Test Coin)", []) is None
