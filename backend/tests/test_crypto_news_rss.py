from unittest.mock import patch

from app.collectors.crypto_news_rss import CryptoNewsRssCollector

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>CryptoPanic</title>
    <item>
      <title>Bitcoin premium hits highest level in 10 weeks</title>
      <link>https://cryptopanic.com/news/1/bitcoin-premium</link>
      <description>BTC on Coinbase trading strong versus Binance.</description>
      <pubDate>Wed, 22 Jul 2026 10:00:00 +0000</pubDate>
    </item>
    <item>
      <title>WOJAK token surges after viral meme revival</title>
      <link>https://cryptopanic.com/news/2/wojak-surge</link>
      <description>A dormant meme format made a comeback this week.</description>
      <pubDate>Thu, 23 Jul 2026 08:30:00 +0000</pubDate>
    </item>
    <item>
      <title>Ethereum staking update</title>
      <link>https://cryptopanic.com/news/3/eth-staking</link>
      <description>No description here.</description>
      <pubDate>invalid-date-format</pubDate>
    </item>
  </channel>
</rss>"""


def make_collector():
    return CryptoNewsRssCollector()


def test_parse_rss_extracts_all_valid_items():
    collector = make_collector()
    entries = collector._parse_rss(SAMPLE_RSS)
    assert len(entries) == 3
    assert entries[0]["title"] == "Bitcoin premium hits highest level in 10 weeks"
    assert entries[1]["title"] == "WOJAK token surges after viral meme revival"


def test_parse_rss_handles_malformed_date_gracefully():
    collector = make_collector()
    entries = collector._parse_rss(SAMPLE_RSS)
    eth_entry = [e for e in entries if "Ethereum" in e["title"]][0]
    assert eth_entry["posted_at"] is None


def test_parse_rss_invalid_xml_returns_empty_not_crash():
    collector = make_collector()
    entries = collector._parse_rss("this is not xml at all <<<")
    assert entries == []


def test_search_matches_coin_symbol_case_insensitively():
    collector = make_collector()
    entries = collector._parse_rss(SAMPLE_RSS)
    matches = collector.search(entries, symbol="wojak", name="Wojak Redemption Arc")
    assert len(matches) == 1
    assert "WOJAK" in matches[0]["text"]


def test_search_no_match_returns_empty():
    collector = make_collector()
    entries = collector._parse_rss(SAMPLE_RSS)
    matches = collector.search(entries, symbol="NONEXISTENTCOIN", name="Totally Unrelated Name")
    assert matches == []


def test_search_respects_limit():
    many_items = "".join(
        f'<item><title>WOJAK news item {i}</title><link>https://x.com/{i}</link>'
        f'<description>desc</description><pubDate>Thu, 23 Jul 2026 08:{i:02d}:00 +0000</pubDate></item>'
        for i in range(20)
    )
    xml_text = f'<?xml version="1.0"?><rss version="2.0"><channel>{many_items}</channel></rss>'
    collector = make_collector()
    entries = collector._parse_rss(xml_text)
    matches = collector.search(entries, symbol="WOJAK", name=None, limit=5)
    assert len(matches) == 5


def test_search_empty_symbol_and_name_returns_empty():
    collector = make_collector()
    entries = collector._parse_rss(SAMPLE_RSS)
    matches = collector.search(entries, symbol="", name=None)
    assert matches == []


def test_get_all_entries_uses_cache_within_ttl():
    from app.collectors.crypto_news_rss import _cache
    _cache["entries"] = None
    _cache["fetched_at"] = 0.0

    collector = make_collector()
    with patch("app.collectors.crypto_news_rss.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_response = mock_client.get.return_value
        mock_response.status_code = 200
        mock_response.text = SAMPLE_RSS

        first = collector.get_all_entries()
        second = collector.get_all_entries()  # should hit cache, not fetch again

        # 6 feeds configured - the first call fetches all 6; the second
        # call should be fully cached, adding zero additional requests.
        assert mock_client.get.call_count == 6
        assert first == second


def test_get_all_entries_one_feed_failing_does_not_block_others():
    from app.collectors.crypto_news_rss import _cache
    _cache["entries"] = None
    _cache["fetched_at"] = 0.0

    collector = make_collector()
    with patch("app.collectors.crypto_news_rss.httpx.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value.__enter__.return_value

        # Simulate: first feed returns a server error, the other five succeed.
        error_response = type("R", (), {"status_code": 500, "text": "server error"})()
        ok_response = type("R", (), {"status_code": 200, "text": SAMPLE_RSS})()
        mock_client.get.side_effect = [error_response] + [ok_response] * 5

        entries = collector.get_all_entries()
        # Five working feeds x 3 entries each = 15, despite one feed failing.
        assert len(entries) == 15
