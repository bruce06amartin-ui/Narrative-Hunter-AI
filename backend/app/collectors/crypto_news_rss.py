"""
Multi-source crypto news RSS collector (MODULE 2: Narrative Scanner - free
bonus source).

This is NOT the same as collectors/cryptopanic.py (the paid per-coin API,
gated on CRYPTOPANIC_API_TOKEN). This fetches several general-purpose,
publicly-published RSS feeds from major crypto news outlets - free,
keyless, no account needed, the same kind of feed any RSS reader would
subscribe to - and matches entries against each coin's symbol/name
client-side, since none of them are filterable by coin server-side.

Feeds included (verified as real, currently-published public feeds):
  - CryptoPanic:    https://cryptopanic.com/news/rss
  - Cointelegraph:  https://cointelegraph.com/rss
  - Decrypt:        https://decrypt.co/feed
  - CryptoSlate:    https://cryptoslate.com/feed
  - Bitcoin.com:    https://news.bitcoin.com/feed
  - Inside Bitcoins: https://insidebitcoins.com/feed

CoinDesk was found in multiple source listings but every one truncated the
exact feed path before I could confirm it - left out rather than guess at
a URL, consistent with how every other integration in this project was
verified before being built.

All feeds are fetched ONCE per scan cycle (not once per coin - that would
be wasteful and rude to free feeds) and results are pooled before matching.

Realistic expectations: these feeds skew toward major coins and
market-wide news (BTC/ETH, macro, DeFi, regulation) - most small/new meme
coins won't show up here at all. Treat this as a free, zero-cost bonus
that occasionally catches real coverage, not a reliable primary source
the way Telegram is.

Standard RSS 2.0 format assumed (title/link/pubDate/description per <item>)
for each feed - not verified against a live fetch in this build environment
(no outbound network access here). Parsing is defensive per-feed AND
per-entry: one feed being down or one entry being malformed doesn't affect
the others.
"""

import logging
import time
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger(__name__)

FEED_URLS = {
    "cryptopanic": "https://cryptopanic.com/news/rss",
    "cointelegraph": "https://cointelegraph.com/rss",
    "decrypt": "https://decrypt.co/feed",
    "cryptoslate": "https://cryptoslate.com/feed",
    "bitcoin.com": "https://news.bitcoin.com/feed",
    "insidebitcoins": "https://insidebitcoins.com/feed",
}
_CACHE_TTL_SECONDS = 240  # refetch at most once per ~4 minutes across a whole cycle
_cache: dict = {"entries": None, "fetched_at": 0.0}


class CryptoNewsRssCollector:
    name = "crypto_news_rss"

    def get_all_entries(self) -> list[dict]:
        """Fetch (or return cached) all configured feeds, pooled into one
        list. Call this ONCE per scan cycle and reuse the result across all
        coins - the feeds are identical for every coin since none are
        per-coin filterable."""
        now = time.time()
        if _cache["entries"] is not None and (now - _cache["fetched_at"]) < _CACHE_TTL_SECONDS:
            return _cache["entries"]

        all_entries: list[dict] = []
        with httpx.Client(timeout=10.0) as client:
            for source_name, url in FEED_URLS.items():
                try:
                    resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; NarrativeHunterAI/0.1)"})
                    if resp.status_code != 200:
                        logger.info("%s RSS fetch miss: %s", source_name, resp.status_code)
                        continue
                    entries = self._parse_rss(resp.text)
                    for e in entries:
                        e["feed_source"] = source_name
                    all_entries.extend(entries)
                except httpx.HTTPError as e:
                    logger.warning("%s RSS fetch failed: %s", source_name, e)
                    continue  # one feed failing doesn't stop the others

        if all_entries:
            _cache["entries"] = all_entries
            _cache["fetched_at"] = now
            return all_entries
        return _cache["entries"] or []

    def _parse_rss(self, xml_text: str) -> list[dict]:
        entries = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning("RSS parse failed: %s", e)
            return entries

        for item in root.findall(".//item"):
            try:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                description = (item.findtext("description") or "").strip()
                pub_date_raw = item.findtext("pubDate")
                posted_at = None
                if pub_date_raw:
                    try:
                        posted_at = parsedate_to_datetime(pub_date_raw)
                        if posted_at.tzinfo is None:
                            posted_at = posted_at.replace(tzinfo=timezone.utc)
                    except (TypeError, ValueError):
                        posted_at = None

                if not title:
                    continue
                entries.append(
                    {
                        "external_id": link or title,
                        "title": title,
                        "text": f"{title} {description}".strip(),
                        "url": link or None,
                        "posted_at": posted_at,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("Skipping malformed RSS entry: %s", e)
        return entries

    def search(self, entries: list[dict], symbol: str, name: str | None, limit: int = 10) -> list[dict]:
        """Client-side filter: entries whose title/description mention the
        coin's symbol or name (substring match, case-insensitive)."""
        if not symbol and not name:
            return []
        needles = {n.lower() for n in (symbol, name) if n}

        matches = []
        for entry in entries:
            haystack = entry["text"].lower()
            if any(needle in haystack for needle in needles):
                matches.append(
                    {
                        "external_id": entry["external_id"],
                        "author": None,
                        "text": entry["title"],
                        "url": entry["url"],
                        "engagement_score": 1.0,  # RSS gives no vote/engagement data - flat weight
                        "posted_at_iso": entry["posted_at"].isoformat() if entry["posted_at"] else None,
                    }
                )
            if len(matches) >= limit:
                break
        return matches
