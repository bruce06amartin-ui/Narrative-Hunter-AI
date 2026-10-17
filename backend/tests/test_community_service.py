from unittest.mock import MagicMock

from app.services.community_service import (
    CommunityIntelligenceService,
    _normalize_text,
    _clip,
    _shingles,
    _jaccard,
)


def make_service():
    return CommunityIntelligenceService(db=MagicMock())


def test_normalize_text_collapses_whitespace_and_case():
    assert _normalize_text("  Hello   WORLD  ") == "hello world"


def test_clip_bounds():
    assert _clip(150, 0, 100) == 100
    assert _clip(-10, 0, 100) == 0
    assert _clip(50, 0, 100) == 50


def test_shingles_short_text_returns_whole_text():
    assert _shingles("hi there", n=3) == {"hi there"}


def test_shingles_produces_overlapping_ngrams():
    result = _shingles("this coin is going to the moon fast", n=3)
    assert "this coin is" in result
    assert "coin is going" in result


def test_jaccard_identical_sets():
    a = {"a", "b", "c"}
    assert _jaccard(a, a) == 1.0


def test_jaccard_disjoint_sets():
    assert _jaccard({"a"}, {"b"}) == 0.0


def test_jaccard_empty_sets():
    assert _jaccard(set(), set()) == 1.0
    assert _jaccard({"a"}, set()) == 0.0


def test_near_duplicate_ratio_catches_templated_spam():
    service = make_service()
    texts = [
        "check out this amazing new coin it just launched and the liquidity "
        "is locked forever the team is fully doxxed and audited buy now before it moons",
        "check out this amazing new coin it just launched and the liquidity "
        "is locked forever the team is fully doxxed and audited buy today before it moons",
        "totally unrelated organic discussion about the roadmap and tokenomics timeline",
    ]
    ratio = service._near_duplicate_ratio(texts)
    assert ratio > 0.0
    assert ratio < 1.0


def test_near_duplicate_ratio_all_unique():
    service = make_service()
    texts = [
        "the roadmap looks promising this quarter",
        "does anyone know the tokenomics breakdown",
        "just aped in after seeing the chart pattern",
    ]
    assert service._near_duplicate_ratio(texts) == 0.0


def test_near_duplicate_ratio_empty_list():
    service = make_service()
    assert service._near_duplicate_ratio([]) == 0.0


def test_community_score_no_components_returns_zero():
    service = make_service()
    metrics = {
        "avg_engagement_per_post": None,
        "organic_discussion_ratio": None,
        "growth_rate_pct": None,
        "duplicate_content_ratio": 0.0,
    }
    assert service._community_score(metrics, reddit_subscribers=None) == 0.0


def test_community_score_high_engagement_high_organic():
    service = make_service()
    metrics = {
        "avg_engagement_per_post": 100.0,  # well above saturation
        "organic_discussion_ratio": 1.0,   # every poster unique
        "growth_rate_pct": 200.0,          # tripled
        "duplicate_content_ratio": 0.0,
    }
    score = service._community_score(metrics, reddit_subscribers=100_000)
    assert score > 85.0


def test_community_score_low_organic_penalizes():
    service = make_service()
    high_organic = service._community_score(
        {
            "avg_engagement_per_post": 20.0,
            "organic_discussion_ratio": 1.0,
            "growth_rate_pct": 0.0,
            "duplicate_content_ratio": 0.0,
        },
        reddit_subscribers=None,
    )
    low_organic = service._community_score(
        {
            "avg_engagement_per_post": 20.0,
            "organic_discussion_ratio": 0.05,  # one account posting almost everything
            "growth_rate_pct": 0.0,
            "duplicate_content_ratio": 0.0,
        },
        reddit_subscribers=None,
    )
    assert high_organic > low_organic


def test_community_score_duplicate_content_penalized():
    service = make_service()
    metrics_base = {
        "avg_engagement_per_post": 20.0,
        "organic_discussion_ratio": 0.8,
        "growth_rate_pct": 10.0,
    }
    clean = service._community_score({**metrics_base, "duplicate_content_ratio": 0.0}, None)
    spammy = service._community_score({**metrics_base, "duplicate_content_ratio": 0.9}, None)
    assert clean > spammy


def test_community_score_bounded_0_to_100():
    service = make_service()
    extreme = service._community_score(
        {
            "avg_engagement_per_post": 1_000_000.0,
            "organic_discussion_ratio": 1.0,
            "growth_rate_pct": 100_000.0,
            "duplicate_content_ratio": 0.0,
        },
        reddit_subscribers=10_000_000,
    )
    assert 0.0 <= extreme <= 100.0


def test_community_score_uses_lunarcrush_when_nothing_else_available():
    service = make_service()
    score = service._community_score(
        {
            "avg_engagement_per_post": None,
            "organic_discussion_ratio": None,
            "growth_rate_pct": None,
            "duplicate_content_ratio": 0.0,
        },
        reddit_subscribers=None,
        lunarcrush_galaxy_score=72.0,
    )
    # Only one component available (lunarcrush) - weighted average of one
    # component equals that component's raw value.
    assert score == 72.0


def test_community_score_blends_lunarcrush_with_post_metrics():
    service = make_service()
    metrics = {
        "avg_engagement_per_post": 20.0,
        "organic_discussion_ratio": 0.8,
        "growth_rate_pct": 10.0,
        "duplicate_content_ratio": 0.0,
    }
    without_lunarcrush = service._community_score(metrics, reddit_subscribers=None)
    with_lunarcrush_high = service._community_score(metrics, reddit_subscribers=None, lunarcrush_galaxy_score=95.0)
    with_lunarcrush_low = service._community_score(metrics, reddit_subscribers=None, lunarcrush_galaxy_score=5.0)

    # A strong external galaxy_score should pull the blended score up;
    # a weak one should pull it down - confirming it's actually blended
    # in, not ignored.
    assert with_lunarcrush_high > without_lunarcrush
    assert with_lunarcrush_low < without_lunarcrush
