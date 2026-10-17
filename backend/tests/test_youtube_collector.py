from unittest.mock import patch

from app.collectors.youtube import YouTubeCollector

SAMPLE_SEARCH_RESPONSE = {
    "items": [
        {
            "id": {"videoId": "abc123"},
            "snippet": {
                "title": "New Coin XYZ Review",
                "description": "Looking at this new token launch",
                "channelTitle": "CryptoReviewer",
                "publishedAt": "2026-07-27T10:00:00Z",
            },
        },
        {
            "id": {"videoId": "def456"},
            "snippet": {
                "title": "XYZ Coin Analysis",
                "description": "Deep dive",
                "channelTitle": "TokenTalk",
                "publishedAt": "2026-07-27T09:00:00Z",
            },
        },
    ]
}

SAMPLE_VIDEOS_RESPONSE = {
    "items": [
        {"id": "abc123", "statistics": {"viewCount": "15000"}},
        {"id": "def456", "statistics": {"viewCount": "500"}},
    ]
}


def make_collector():
    return YouTubeCollector()


def test_is_configured_true_with_key():
    collector = make_collector()
    with patch("app.collectors.youtube.settings.youtube_api_key", "fake-key"):
        assert collector.is_configured() is True


def test_is_configured_false_without_key():
    collector = make_collector()
    with patch("app.collectors.youtube.settings.youtube_api_key", None):
        assert collector.is_configured() is False


def test_search_recent_videos_parses_correctly():
    collector = make_collector()
    with patch("app.collectors.youtube.settings.youtube_api_key", "fake-key"), \
         patch("app.collectors.youtube.get_json", return_value=SAMPLE_SEARCH_RESPONSE):
        results = collector.search_recent_videos('"XYZ" crypto', "2026-07-24T00:00:00Z")

    assert len(results) == 2
    assert results[0]["video_id"] == "abc123"
    assert results[0]["title"] == "New Coin XYZ Review"
    assert results[0]["channel_title"] == "CryptoReviewer"


def test_search_recent_videos_not_configured_returns_empty_no_call():
    collector = make_collector()
    with patch("app.collectors.youtube.settings.youtube_api_key", None), \
         patch("app.collectors.youtube.get_json") as mock_get:
        results = collector.search_recent_videos('"XYZ" crypto', "2026-07-24T00:00:00Z")
    assert results == []
    mock_get.assert_not_called()


def test_search_recent_videos_handles_api_failure():
    from app.collectors.base import CollectorHTTPError
    collector = make_collector()
    with patch("app.collectors.youtube.settings.youtube_api_key", "fake-key"), \
         patch("app.collectors.youtube.get_json", side_effect=CollectorHTTPError("boom")):
        results = collector.search_recent_videos('"XYZ" crypto', "2026-07-24T00:00:00Z")
    assert results == []


def test_search_recent_videos_skips_entries_without_video_id():
    collector = make_collector()
    broken = {"items": [{"id": {}, "snippet": {"title": "no id"}}, SAMPLE_SEARCH_RESPONSE["items"][0]]}
    with patch("app.collectors.youtube.settings.youtube_api_key", "fake-key"), \
         patch("app.collectors.youtube.get_json", return_value=broken):
        results = collector.search_recent_videos('"XYZ" crypto', "2026-07-24T00:00:00Z")
    assert len(results) == 1
    assert results[0]["video_id"] == "abc123"


def test_get_view_counts_parses_correctly():
    collector = make_collector()
    with patch("app.collectors.youtube.settings.youtube_api_key", "fake-key"), \
         patch("app.collectors.youtube.get_json", return_value=SAMPLE_VIDEOS_RESPONSE):
        counts = collector.get_view_counts(["abc123", "def456"])

    assert counts == {"abc123": 15000, "def456": 500}


def test_get_view_counts_empty_list_returns_empty_no_call():
    collector = make_collector()
    with patch("app.collectors.youtube.settings.youtube_api_key", "fake-key"), \
         patch("app.collectors.youtube.get_json") as mock_get:
        counts = collector.get_view_counts([])
    assert counts == {}
    mock_get.assert_not_called()


def test_get_view_counts_batches_over_50_ids():
    collector = make_collector()
    ids = [f"vid{i}" for i in range(120)]
    call_count = {"n": 0}

    def fake_get_json(url, params):
        call_count["n"] += 1
        return {"items": []}

    with patch("app.collectors.youtube.settings.youtube_api_key", "fake-key"), \
         patch("app.collectors.youtube.get_json", side_effect=fake_get_json):
        collector.get_view_counts(ids)

    assert call_count["n"] == 3


def test_get_view_counts_api_failure_on_one_batch_still_returns_others():
    from app.collectors.base import CollectorHTTPError
    collector = make_collector()
    ids = [f"vid{i}" for i in range(60)]

    call_count = {"n": 0}

    def fake_get_json(url, params):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise CollectorHTTPError("boom")
        return SAMPLE_VIDEOS_RESPONSE

    with patch("app.collectors.youtube.settings.youtube_api_key", "fake-key"), \
         patch("app.collectors.youtube.get_json", side_effect=fake_get_json):
        counts = collector.get_view_counts(ids)

    assert counts == {"abc123": 15000, "def456": 500}
