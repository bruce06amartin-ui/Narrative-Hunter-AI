"""
Telegram public-channel collector (MODULE 2: Narrative Scanner).

This was previously left unimplemented because there was no reliable way
to know *which* Telegram channel corresponds to a given coin. That's now
solved: GeckoTerminal's token info endpoint
(GET /networks/{network}/tokens/{address}/info) returns the project's own
declared telegram_handle - see collectors/geckoterminal.py:get_token_info()
and discovery_service.py, which stores it on Coin.telegram_handle at
discovery time.

This collector scrapes Telegram's public channel preview
(https://t.me/s/{handle}) - no bot token or login required, but also no
official API or stability guarantee. It's HTML scraping: if Telegram
changes their markup, this breaks. There's no way to verify that hasn't
happened without live network access, so treat parse failures as
"this channel yielded nothing" (logged, not raised) rather than a hard error.

Only works for channels that are PUBLIC (have a t.me/{handle} short link);
private/invite-only groups aren't accessible this way, which is most of
them for smaller projects.
"""

import logging
import re
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://t.me/s"

# Matches one message block's text content and its ISO timestamp.
# Telegram's preview markup wraps message text in a div with this class,
# and includes a <time datetime="..."> element for the post time.
_MESSAGE_TEXT_RE = re.compile(
    r'tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.DOTALL
)
_TIME_RE = re.compile(r'<time[^>]*datetime="([^"]+)"')
_TAG_RE = re.compile(r"<[^>]+>")
_VIEWS_RE = re.compile(r'tgme_widget_message_views">([\d.,KM]+)<')


class TelegramPublicCollector:
    name = "telegram"

    def get_recent_messages(self, handle: str, limit: int = 25) -> list[dict]:
        if not handle:
            return []

        url = f"{BASE_URL}/{handle.lstrip('@')}"
        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; NarrativeHunterAI/0.1)"})
                if resp.status_code != 200:
                    logger.info("Telegram preview miss for %s: %s", handle, resp.status_code)
                    return []
                html = resp.text
        except httpx.HTTPError as e:
            logger.warning("Telegram preview request failed for %s: %s", handle, e)
            return []

        return self._parse_messages(html, handle, limit)

    def _parse_messages(self, html: str, handle: str, limit: int) -> list[dict]:
        text_matches = list(_MESSAGE_TEXT_RE.finditer(html))
        time_matches = list(_TIME_RE.finditer(html))
        view_matches = list(_VIEWS_RE.finditer(html))

        posts = []
        # Telegram's preview page lists messages oldest-first; take the tail
        # (most recent) up to `limit`.
        for i, text_match in enumerate(text_matches[-limit:]):
            try:
                raw_html_fragment = text_match.group(1)
                text = _TAG_RE.sub(" ", raw_html_fragment)
                text = _unescape_basic_entities(text).strip()
                if not text:
                    continue

                idx = len(text_matches) - min(limit, len(text_matches)) + i
                timestamp = None
                if idx < len(time_matches):
                    timestamp = _parse_iso(time_matches[idx].group(1))

                views = 0.0
                if idx < len(view_matches):
                    views = _parse_view_count(view_matches[idx].group(1))

                posts.append(
                    {
                        "external_id": f"{handle}:{idx}",
                        "author": handle,
                        "text": text,
                        "url": f"https://t.me/{handle}",
                        "engagement_score": views,
                        "posted_at_iso": timestamp.isoformat() if timestamp else None,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("Skipping malformed Telegram message for %s: %s", handle, e)
        return posts


def _unescape_basic_entities(text: str) -> str:
    return (
        text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
        .replace("\xa0", " ")
    )


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_view_count(value: str) -> float:
    value = value.strip().upper()
    try:
        if value.endswith("K"):
            return float(value[:-1]) * 1_000
        if value.endswith("M"):
            return float(value[:-1]) * 1_000_000
        return float(value.replace(",", ""))
    except ValueError:
        return 0.0
