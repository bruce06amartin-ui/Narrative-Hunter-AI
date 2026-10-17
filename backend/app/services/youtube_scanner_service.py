"""
MODULE 2 extension: YouTube narrative scanning.

Adds crypto YouTuber coverage as a source feeding the existing
SocialPost / community_score / narrative_score pipeline - the same
pipeline Telegram and RSS already feed, reused here rather than building
a parallel scoring path (see NarrativeScannerService._store_posts, which
this service calls directly).

BUDGET: see config.py's youtube_* settings for the worked-out request
math against the real free tier (10,000 quota units/day, confirmed via
multiple independent sources - search.list costs 100 units/call, the
dominant cost). Bounded the same way as risk/wallet/price-refresh: only
new-or-stale coins get checked each cycle (youtube_recheck_hours), only
up to youtube_max_coins_per_cycle per cycle, prioritized by liquidity.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.collectors.youtube import YouTubeCollector
from app.config import settings
from app.models.coin import Coin
from app.models.score import Score
from app.services.narrative_scanner_service import NarrativeScannerService

logger = logging.getLogger(__name__)


class YouTubeScannerService:
    def __init__(self, db: Session):
        self.db = db
        self.collector = YouTubeCollector()
        # Reused purely for its _store_posts dedup/storage logic - keeps
        # SocialPost writes in one place rather than duplicating them.
        self._narrative_service = NarrativeScannerService(db)

    def scan_cycle(self) -> dict:
        if not self.collector.is_configured():
            return {
                "skipped": True,
                "reason": "YOUTUBE_API_KEY not configured",
                "ran_at": datetime.utcnow().isoformat(),
            }

        recheck_cutoff = datetime.utcnow() - timedelta(hours=settings.youtube_recheck_hours)
        coins = (
            self.db.query(Coin)
            .outerjoin(Score, Score.coin_id == Coin.id)
            .filter(
                Coin.is_active.is_(True),
                (Score.id.is_(None))
                | (Score.youtube_checked_at.is_(None))
                | (Score.youtube_checked_at < recheck_cutoff),
            )
            .order_by(Coin.liquidity_usd.desc())
            .limit(settings.youtube_max_coins_per_cycle)
            .all()
        )

        published_after = (
            datetime.now(timezone.utc) - timedelta(days=settings.youtube_search_lookback_days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        total_new_posts = 0
        coins_processed = 0
        all_found_videos: list[dict] = []  # (coin, video dict) pairs, collected before the batched stats call

        for coin in coins:
            coin_id_for_logging = coin.id
            try:
                query = self._build_search_query(coin)
                if query is None:
                    # Neither symbol nor name has anything searchable (a
                    # real pattern found in production data: some coins
                    # use blank/invisible Unicode characters as their
                    # symbol - the same low-quality pattern already
                    # flagged by the liquidity manipulation filter). A
                    # search here would be guaranteed to find nothing, so
                    # skip it entirely - saves quota, and correctly marks
                    # the coin checked so it doesn't get retried forever.
                    self._mark_checked(coin)
                    self.db.commit()
                    coins_processed += 1
                    continue

                videos = self.collector.search_recent_videos(query, published_after)
                for v in videos:
                    all_found_videos.append((coin, v))
                self._mark_checked(coin)
                self.db.commit()
                coins_processed += 1
            except Exception:  # noqa: BLE001 - one bad coin shouldn't kill the run
                self.db.rollback()
                logger.exception("YouTube scan failed for coin id=%s", coin_id_for_logging)

        # One cheap batched call (or a few, chunked by 50) for view counts
        # across EVERY video found this cycle, instead of a per-video call.
        video_ids = [v["video_id"] for _, v in all_found_videos]
        view_counts = self.collector.get_view_counts(video_ids)

        for coin, v in all_found_videos:
            try:
                post = {
                    "source": "youtube",
                    "external_id": v["video_id"],
                    "author": v.get("channel_title"),
                    "text": f"{v.get('title', '')}\n\n{v.get('description', '')}".strip(),
                    "url": f"https://www.youtube.com/watch?v={v['video_id']}",
                    "engagement_score": float(view_counts.get(v["video_id"], 0)),
                    "posted_at_iso": v.get("published_at"),
                }
                new_count = self._narrative_service._store_posts(coin, [post])
                total_new_posts += new_count
                self.db.commit()
            except Exception:  # noqa: BLE001
                self.db.rollback()
                logger.exception("Failed storing YouTube post for coin id=%s", coin.id)

        return {
            "coins_processed": coins_processed,
            "due_for_check_this_cycle": len(coins),
            "videos_found": len(all_found_videos),
            "new_posts_stored": total_new_posts,
            "ran_at": datetime.utcnow().isoformat(),
        }

    # Unicode characters specifically designed to be invisible/filler,
    # despite some being categorized as Letters (confirmed via testing:
    # HANGUL FILLER returns True from isalnum() and Unicode categorizes
    # it as "Lo" - Letter, other - the same category as a real letter, so
    # isalnum() alone cannot distinguish it from genuine text). Found as
    # a real, repeated pattern in production data: several coins used
    # this exact character as their symbol, always alongside other
    # manipulation red flags. This is an explicit blocklist, not a
    # complete general solution - new evasion characters could exist
    # that aren't listed here.
    _INVISIBLE_CHARS = frozenset(
        "\u3164\u115F\u1160\u200B\u200C\u200D\u180E\uFEFF"
    )

    def _build_search_query(self, coin: Coin) -> str | None:
        """Requires "meme coin" phrasing alongside the quoted symbol/name
        - found via real data that a coin named "Robinhood" mostly
        matched videos about the actual trading app, not the token; the
        "meme coin" qualifier is what actually disambiguates that
        (real-world Robinhood content rarely gets called "Robinhood
        meme coin"). An earlier version of this also required a literal
        $ cashtag, but that turned out to be too strict in the other
        direction - even a coin as famous and heavily-covered as
        Fartcoin returned zero results, since most casual video titles
        just say the name without a cashtag. Dropped the cashtag
        requirement, kept the "meme coin" qualifier.

        Falls back to the coin's NAME when the symbol itself is blank or
        made of invisible Unicode filler characters - a real pattern
        found in production data, which would otherwise produce a search
        guaranteed to find nothing. Returns None if neither symbol nor
        name has anything searchable at all."""
        if self._has_searchable_text(coin.symbol):
            return f'"{coin.symbol}" meme coin'
        if self._has_searchable_text(coin.name):
            return f'"{coin.name}" meme coin'
        return None

    @classmethod
    def _has_searchable_text(cls, value: str | None) -> bool:
        """True if value contains at least one real alphanumeric
        character after stripping known invisible-filler characters.
        isalnum() alone is NOT sufficient here - verified that it
        returns True for HANGUL FILLER, which is Unicode category "Lo"
        (Letter, other), the same category as genuine letters."""
        if not value:
            return False
        cleaned = "".join(ch for ch in value if ch not in cls._INVISIBLE_CHARS)
        return any(ch.isalnum() for ch in cleaned)

    def _mark_checked(self, coin: Coin) -> None:
        score = self.db.query(Score).filter(Score.coin_id == coin.id).first()
        if score is None:
            score = Score(coin_id=coin.id)
            self.db.add(score)
        score.youtube_checked_at = datetime.utcnow()
        self.db.flush()
