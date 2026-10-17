from unittest.mock import MagicMock

from app.services.narrative_scanner_service import NarrativeScannerService


class FakeCoin:
    id = "coin-1"
    symbol = "TEST"
    name = "Test Coin"
    contract_address = "0xabcdef1234567890"
    telegram_handle = "test_channel"


def make_service():
    service = NarrativeScannerService(db=MagicMock())
    service.reddit.is_configured = MagicMock(return_value=False)
    service.cryptopanic.is_configured = MagicMock(return_value=False)
    service.twitter.is_configured = MagicMock(return_value=False)
    service.telegram.get_recent_messages = MagicMock(return_value=[{"text": "hello", "external_id": "1"}])
    service._store_posts = MagicMock(return_value=1)
    return service


def test_allow_ai_false_skips_analysis_even_when_ai_configured_and_posts_exist():
    service = make_service()
    service.ai.is_configured = MagicMock(return_value=True)
    service.ai.analyze = MagicMock()

    result = service.scan_coin(FakeCoin(), rss_entries=None, allow_ai=False)

    assert result["analyzed"] is False
    service.ai.analyze.assert_not_called()
    service._store_posts.assert_called_once()


def test_allow_ai_true_with_ai_configured_analyzes():
    service = make_service()
    service.ai.is_configured = MagicMock(return_value=True)
    service.ai.analyze = MagicMock(return_value={"narrative_score": 70.0})
    service._store_narrative = MagicMock()

    result = service.scan_coin(FakeCoin(), rss_entries=None, allow_ai=True)

    assert result["analyzed"] is True
    service.ai.analyze.assert_called_once()


def test_allow_ai_true_but_ai_not_configured_does_not_analyze():
    service = make_service()
    service.ai.is_configured = MagicMock(return_value=False)
    service.ai.analyze = MagicMock()

    result = service.scan_coin(FakeCoin(), rss_entries=None, allow_ai=True)

    assert result["analyzed"] is False
    service.ai.analyze.assert_not_called()


def test_narrative_checked_at_set_regardless_of_ai_outcome():
    service = make_service()
    service.ai.is_configured = MagicMock(return_value=True)

    fake_score = MagicMock()
    service.db.query.return_value.filter.return_value.first.return_value = fake_score

    service.scan_coin(FakeCoin(), rss_entries=None, allow_ai=False)

    assert fake_score.narrative_checked_at is not None


class FakeCoinNoLiveSource:
    """No Telegram handle at all - isolates the exact real-world case
    that prompted this fix: a coin with genuinely existing posts (e.g.
    from YouTube), but no live source configured/available for it."""
    id = "coin-no-live-source"
    symbol = "NOLIVESRC"
    name = "No Live Source Coin"
    contract_address = "0xabcdef1234567890"
    telegram_handle = None


class FakeExistingPost:
    def __init__(self, source, external_id, text, engagement_score=5.0):
        self.source = source
        self.external_id = external_id
        self.author = "some_author"
        self.text = text
        self.url = "https://example.com/post"
        self.engagement_score = engagement_score
        self.community = None


def test_existing_posts_from_other_collectors_reach_ai_analysis():
    """The exact real-world bug found via live testing: a coin with
    confirmed real YouTube posts still produced coins_analyzed_by_ai=0
    every cycle, because scan_coin only ever looked at posts freshly
    fetched live within the same function call (Reddit/CryptoPanic/
    Twitter/Telegram/RSS) - never at what already existed in the DB
    from a separate collector like the YouTube scanner. This confirms
    existing posts now correctly reach the AI."""
    service = make_service()
    coin = FakeCoinNoLiveSource()

    existing_youtube_post = FakeExistingPost(
        source="youtube", external_id="yt-123", text="Real YouTube video about this coin"
    )
    service.db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        existing_youtube_post
    ]

    service.ai.is_configured = MagicMock(return_value=True)
    service.ai.analyze = MagicMock(return_value={"narrative_score": 70.0, "reasoning": "test"})

    result = service.scan_coin(coin, rss_entries=None, allow_ai=True)

    assert result["analyzed"] is True
    service.ai.analyze.assert_called_once()
    call_args = service.ai.analyze.call_args
    posts_passed_to_ai = call_args[0][1]
    assert len(posts_passed_to_ai) == 1
    assert posts_passed_to_ai[0]["source"] == "youtube"
    assert posts_passed_to_ai[0]["text"] == "Real YouTube video about this coin"
