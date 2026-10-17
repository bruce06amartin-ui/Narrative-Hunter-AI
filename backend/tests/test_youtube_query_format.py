from unittest.mock import MagicMock, patch

from app.services.youtube_scanner_service import YouTubeScannerService


class FakeCoin:
    def __init__(self, id, symbol):
        self.id = id
        self.symbol = symbol


def test_search_query_uses_meme_coin_phrasing_without_overly_strict_cashtag():
    """v1 of this fix required a literal $ cashtag alongside 'meme coin',
    which correctly fixed the original false-positive problem (a coin
    named 'Robinhood' matching videos about the real trading app) but
    turned out too strict in the OTHER direction: even Fartcoin, a
    famous, heavily-covered meme coin, returned zero results, since
    casual video titles don't use cashtag notation. Settled on "meme
    coin" alone as the disambiguator, without requiring the cashtag."""
    fake_coin = FakeCoin(id="coin-1", symbol="Robinhood")

    service = YouTubeScannerService(db=MagicMock())
    service.collector = MagicMock()
    service.collector.is_configured.return_value = True
    service.collector.search_recent_videos.return_value = []
    service.collector.get_view_counts.return_value = {}

    with patch.object(YouTubeScannerService, "_mark_checked"):
        service.db.query.return_value.outerjoin.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [fake_coin]
        service.scan_cycle()

    called_query = service.collector.search_recent_videos.call_args[0][0]
    assert called_query == '"Robinhood" meme coin'
    assert "crypto" not in called_query.lower()
    assert "$" not in called_query
