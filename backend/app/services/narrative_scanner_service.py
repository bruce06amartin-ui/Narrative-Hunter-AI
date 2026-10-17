"""
MODULE 2: Narrative Scanner.

Sources and status:
  - Reddit          -> IMPLEMENTED (OAuth2 client-credentials, gated on
                       REDDIT_CLIENT_ID/SECRET - see collectors/reddit.py
                       for why getting credentials got much harder in 2026)
  - Crypto news      -> IMPLEMENTED (CryptoPanic's paid per-coin API, gated on
                       CRYPTOPANIC_API_TOKEN) PLUS a free bonus source:
                       CryptoPanic's general public RSS feed (no key needed,
                       see collectors/crypto_news_rss.py) - fetched once per
                       cycle and matched client-side against each coin's
                       symbol/name. Realistically only catches coverage for
                       coins that get genuine news attention, not most small
                       meme coins, but it's a real zero-cost bonus.
  - X posts          -> IMPLEMENTED (gated on TWITTER_BEARER_TOKEN - X has no
                       free tier as of Feb 2026, see collectors/twitter.py)
  - Public Telegram   -> IMPLEMENTED for PUBLIC channels, using GeckoTerminal's
    channels             token-info endpoint (free, keyless) to learn a coin's
                       declared telegram_handle, then scraping the public
                       t.me/s/{handle} preview page. No bot token needed, but
                       it's HTML scraping with no stability guarantee (see
                       collectors/telegram_public.py) and only reaches coins
                       that both (a) set a Telegram link on GeckoTerminal and
                       (b) have a public (not invite-only) channel.
  - Google Trends     -> PENDING. No official free API; the realistic path
                       (pytrends, an unofficial scraper) is fragile and
                       against Google's ToS at scale - not built without a
                       way to verify it holds up.

Every source above is independently optional - if none are configured,
`check_all_active` returns immediately having done nothing, and
narrative_score simply stays null (consistent with how RiskService/
WalletIntelligenceService handle missing optional data).
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.collectors.cryptopanic import CryptoPanicCollector
from app.collectors.crypto_news_rss import CryptoNewsRssCollector
from app.collectors.reddit import RedditCollector
from app.collectors.telegram_public import TelegramPublicCollector
from app.collectors.twitter import TwitterCollector
from app.config import settings
from app.models.coin import Coin
from app.models.narrative import Narrative
from app.models.score import Score
from app.models.social_post import SocialPost
from app.services.narrative_ai_service import NarrativeAIService

logger = logging.getLogger(__name__)


class NarrativeScannerService:
    def __init__(self, db: Session):
        self.db = db
        self.reddit = RedditCollector()
        self.cryptopanic = CryptoPanicCollector()
        self.crypto_news_rss = CryptoNewsRssCollector()
        self.twitter = TwitterCollector()
        self.telegram = TelegramPublicCollector()
        self.ai = NarrativeAIService()


    def any_source_configured(self) -> bool:
        # Telegram is keyless (gated per-coin on having a telegram_handle,
        # not on any global config), so there's always at least one
        # potential source - Reddit/CryptoPanic/X just add more coverage.
        return True

    def check_all_active(self) -> dict:
        if not self.any_source_configured():
            return {
                "skipped": True,
                "reason": "no narrative sources configured (Reddit/CryptoPanic/X all unset)",
                "ran_at": datetime.utcnow().isoformat(),
            }

        # Free-source scanning (Telegram/RSS collection, community-relevant
        # post storage) is bounded ONLY by liquidity + staleness, same
        # pattern as risk/wallet - there's no cost risk in checking MORE
        # coins here, since Telegram and the RSS feeds are both free and
        # keyless. Only the AI ANALYSIS step below has a real cost, and
        # that's capped separately by narrative_max_coins_per_cycle,
        # applied per-cycle regardless of how many coins get scanned for
        # free sources. This split was a real gap found via production
        # data: the old code applied ONE flat limit to both, meaning free
        # Telegram/RSS coverage was silently capped at 15 coins/cycle even
        # though Anthropic wasn't even configured yet (zero cost risk).
        recheck_cutoff = datetime.utcnow() - timedelta(hours=settings.narrative_recheck_hours)
        coins = (
            self.db.query(Coin)
            .outerjoin(Score, Score.coin_id == Coin.id)
            .filter(
                Coin.is_active.is_(True),
                Coin.liquidity_usd >= settings.narrative_min_liquidity_usd,
                (Score.id.is_(None))
                | (Score.narrative_checked_at.is_(None))
                | (Score.narrative_checked_at < recheck_cutoff),
            )
            # Prioritize by CURRENT overall_score, not raw liquidity.
            # Real gap found in production: repeated health checks kept
            # showing the same top-liquidity coins sitting at 58-62 with
            # narrative_score still null, cycle after cycle, while a
            # bounded 15-per-cycle AI budget got spent on whichever coins
            # happened to be liquidity-ranked highest - not necessarily
            # the ones actually close to crossing 70. Ordering by
            # existing overall_score instead concentrates the limited
            # narrative budget on coins that are already strong on every
            # OTHER signal and are genuinely one real narrative_score away
            # from crossing the threshold - without changing what counts
            # as a good score at all, just who gets checked first.
            # Coalesced to -1 so completely unscored coins (no Score row
            # yet) sort last, behind anything with a real, meaningful
            # score already - they're not "near a threshold" yet at all.
            .order_by(func.coalesce(Score.overall_score, -1).desc())
            .all()
        )
        scanned = 0
        analyzed = 0
        no_source_available = 0
        ai_analyses_this_cycle = 0
        rss_entries = self.crypto_news_rss.get_all_entries()  # fetched once, reused for every coin this cycle
        for coin in coins:
            coin_id_for_logging = coin.id
            if not self._has_any_source(coin):
                no_source_available += 1
            allow_ai = ai_analyses_this_cycle < settings.narrative_max_coins_per_cycle
            try:
                result = self.scan_coin(coin, rss_entries, allow_ai=allow_ai)
                self.db.commit()  # commit per-coin so one later failure can't roll back earlier successes
                scanned += 1
                if result.get("analyzed"):
                    analyzed += 1
                    ai_analyses_this_cycle += 1
            except Exception:  # noqa: BLE001 - one bad coin shouldn't kill the run
                self.db.rollback()
                logger.exception("Narrative scan failed for coin id=%s", coin_id_for_logging)
        return {
            "coins_scanned": scanned,
            "coins_analyzed_by_ai": analyzed,
            "coins_with_no_source_available": no_source_available,
            "ai_configured": self.ai.is_configured(),
            "ai_analysis_cap_this_cycle": settings.narrative_max_coins_per_cycle,
            "total_eligible": len(coins),
            "ran_at": datetime.utcnow().isoformat(),
        }

    def _existing_posts(self, coin: Coin) -> list[dict]:
        """Posts already sitting in the DB for this coin from a SEPARATE
        collector (chiefly YouTube, which runs on its own schedule and
        writes to the same social_posts table, but was previously never
        being re-read by this function - meaning the AI never saw
        YouTube-sourced content at all, regardless of how much of it
        existed). Bounded to a recent lookback window so we're not
        feeding the AI stale, no-longer-relevant posts from long ago."""
        cutoff = datetime.utcnow() - timedelta(hours=settings.narrative_existing_post_lookback_hours)
        rows = (
            self.db.query(SocialPost)
            .filter(SocialPost.coin_id == coin.id, SocialPost.collected_at >= cutoff)
            .order_by(SocialPost.collected_at.desc())
            .limit(20)
            .all()
        )
        return [
            {
                "source": r.source,
                "external_id": r.external_id,
                "author": r.author,
                "text": r.text,
                "url": r.url,
                "engagement_score": r.engagement_score,
                "subreddit": r.community,
            }
            for r in rows
        ]

    def _has_any_source(self, coin: Coin) -> bool:
        """A coin only has something LIKELY to work if at least one
        reasonably reliable source can be checked for it: a configured
        Reddit/CryptoPanic/X key (checks ANY coin), or a Telegram handle
        GeckoTerminal reported for THIS specific coin. The free RSS feed
        (crypto_news_rss) is deliberately NOT counted here even though it's
        always attempted - it skews toward major-coin/market news and will
        find nothing for the vast majority of small meme coins, so counting
        it would make coins_with_no_source_available misleadingly optimistic
        (technically "checked," but very unlikely to actually find anything).
        If none of these are true, coins_with_no_source_available counts it -
        that's the concrete number to look at when narrative coverage seems
        low: it tells you whether it's a config gap (add a source) or just
        that most of your coins don't have social links set."""
        return (
            self.reddit.is_configured()
            or self.cryptopanic.is_configured()
            or self.twitter.is_configured()
            or bool(coin.telegram_handle)
        )

    def scan_coin(self, coin: Coin, rss_entries: list[dict] | None = None, allow_ai: bool = True) -> dict:
        query = coin.symbol or coin.name or ""
        if not query:
            return {"analyzed": False}

        collected: list[dict] = []
        if self.reddit.is_configured():
            for p in self.reddit.search(f'"{query}"'):
                collected.append({**p, "source": "reddit"})
        if self.cryptopanic.is_configured() and coin.symbol:
            for p in self.cryptopanic.get_posts(coin.symbol):
                collected.append({**p, "source": "cryptopanic"})
        if self.twitter.is_configured():
            for p in self.twitter.search(f'"{query}"'):
                collected.append({**p, "source": "twitter"})
        if coin.telegram_handle:
            for p in self.telegram.get_recent_messages(coin.telegram_handle):
                collected.append({**p, "source": "telegram"})
        if rss_entries:
            for p in self.crypto_news_rss.search(rss_entries, coin.symbol or "", coin.name):
                collected.append({**p, "source": "crypto_news_rss"})

        collected.extend(self._existing_posts(coin))

        new_count = self._store_posts(coin, collected)

        if not allow_ai or not self.ai.is_configured() or not collected:
            self._set_narrative_score(coin, None)
            return {"analyzed": False, "posts_collected": len(collected), "posts_new": new_count}

        coin_label = f"{coin.symbol or coin.contract_address[:8]} ({coin.name or 'unknown name'})"
        analysis = self.ai.analyze(coin_label, collected)
        if analysis is None:
            self._set_narrative_score(coin, None)
            return {"analyzed": False, "posts_collected": len(collected), "posts_new": new_count}

        self._store_narrative(coin, analysis, len(collected), collected)
        self._set_narrative_score(coin, analysis.get("narrative_score"))
        return {"analyzed": True, "posts_collected": len(collected), "posts_new": new_count}

    def _store_posts(self, coin: Coin, posts: list[dict]) -> int:
        new_count = 0
        for p in posts:
            exists = (
                self.db.query(SocialPost)
                .filter(
                    SocialPost.coin_id == coin.id,
                    SocialPost.source == p["source"],
                    SocialPost.external_id == p["external_id"],
                )
                .first()
            )
            if exists:
                continue

            posted_at = self._parse_posted_at(p)
            self.db.add(
                SocialPost(
                    coin_id=coin.id,
                    source=p["source"],
                    external_id=p["external_id"],
                    author=p.get("author"),
                    text=p.get("text", ""),
                    url=p.get("url"),
                    engagement_score=p.get("engagement_score", 0.0),
                    community=p.get("subreddit"),
                    posted_at=posted_at,
                )
            )
            new_count += 1
        self.db.flush()
        return new_count

    def _parse_posted_at(self, post: dict):
        if post.get("posted_at_epoch"):
            return datetime.utcfromtimestamp(post["posted_at_epoch"])
        if post.get("posted_at_iso"):
            try:
                return datetime.fromisoformat(post["posted_at_iso"].replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    def _store_narrative(self, coin: Coin, analysis: dict, post_count: int, posts: list[dict]) -> None:
        narrative = self.db.query(Narrative).filter(Narrative.coin_id == coin.id).first()
        if narrative is None:
            narrative = Narrative(coin_id=coin.id)
            self.db.add(narrative)

        sources_used = sorted({p["source"] for p in posts})

        for field in (
            "main_topic", "meme_category", "related_events", "similar_historical_memes",
            "emotion", "is_funny", "is_controversial", "is_relatable",
            "could_spread_beyond_crypto", "narrative_summary", "virality_score", "narrative_score",
        ):
            setattr(narrative, field, analysis.get(field))

        narrative.post_count_analyzed = post_count
        narrative.sources_used = ",".join(sources_used)
        self.db.flush()

    def _set_narrative_score(self, coin: Coin, narrative_score: float | None) -> None:
        score = self.db.query(Score).filter(Score.coin_id == coin.id).first()
        if score is None:
            score = Score(coin_id=coin.id)
            self.db.add(score)
        score.narrative_score = narrative_score
        score.narrative_checked_at = datetime.utcnow()
        self.db.flush()
