from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg2://nha:nha_password@localhost:5432/narrative_hunter"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Discovery
    discovery_networks: str = "solana,eth,base"
    discovery_interval_seconds: int = 120
    # How often existing coins get a fresh price/liquidity/volume check,
    # independent of the new_pools discovery feed - see
    # DiscoveryService.refresh_existing_prices() for why this matters.
    # ~1700 coins / 30 per batch ≈ 57 batches, at the shared ~2.2s
    # GeckoTerminal throttle that's ~2 minutes for a full pass, so this
    # interval has generous headroom even at real scale.
    price_refresh_interval_seconds: int = 600
    # Same bounded-recheck pattern as risk_recheck_hours/wallet_recheck_hours -
    # only coins new or not refreshed within this window get checked each
    # cycle, once the initial catch-up pass completes.
    price_refresh_recheck_hours: int = 2
    # Social handle re-enrichment now runs on its own schedule, decoupled
    # from discovery_interval_seconds - previously it shared discovery's
    # tight 120s window, which capped how many coins could be re-checked
    # per cycle without risking the same overlap problem already fixed for
    # risk/wallet/price-refresh. 150 coins * ~2.2s throttle ≈ 330s, so this
    # interval gives real headroom.
    social_reenrichment_interval_seconds: int = 600
    risk_interval_seconds: int = 150
    # Only re-check a coin's risk if it's never been checked, or its last
    # check is older than this many hours. Without this bound, every cycle
    # blindly re-scans ALL active coins - at real scale (1000+ coins), a
    # full throttled pass can take longer than risk_interval_seconds
    # itself, so cycles perpetually overlap and never reliably catch up
    # (confirmed via real production data: a coin went 18+ hours without
    # completing a single risk check under the old unbounded approach).
    risk_recheck_hours: int = 6
    trend_interval_seconds: int = 160
    # Sniper-cluster detection (MODULE 5): flag when this many distinct
    # wallets have a first buy within this many seconds of launch_time.
    sniper_cluster_window_seconds: int = 60
    sniper_cluster_min_wallets: int = 5
    # Repeat-deployer detection (MODULE 5): flag when a creator_address has
    # deployed at least this many OTHER tracked coins on the same chain.
    repeat_deployer_min_other_coins: int = 2
    scoring_interval_seconds: int = 180

    # Scoring weights as fractions of the full MODULE 8 spec (Narrative 25 /
    # Community 20 / Wallets 20 / Risk -20 / Liquidity 10 / Trend 15, i.e.
    # /100). ScoringService computes a weighted average across whichever of
    # {liquidity, trend, wallet} are actually available for a given coin,
    # which naturally preserves these relative ratios no matter which subset
    # is present (narrative/community stay excluded until those modules exist).
    weight_liquidity: float = 0.10
    weight_trend: float = 0.15
    weight_wallet: float = 0.20
    weight_narrative: float = 0.25
    weight_community: float = 0.20
    # Subtractive penalty weight for risk_score (MODULE 5) - matches the
    # spec's "-20%" exactly; applied after the weighted average above, not
    # part of that pool, since Risk is a negative weight in the spec.
    weight_risk_penalty: float = 0.20

    app_env: str = "development"
    log_level: str = "INFO"

    # --- MODULE 9: Alerts ---
    alert_interval_seconds: int = 90
    # Fires once when a coin's overall_score crosses from below to at/above this.
    alert_overall_score_threshold: float = 70.0
    # Fires when risk_score moves by at least this many points between two
    # consecutive scoring cycles (either direction - a big drop is worth
    # knowing about too, e.g. liquidity just got locked).
    alert_risk_score_change_threshold: float = 20.0
    # Applied to overall/narrative/community threshold alerts: skip firing
    # if risk_score is confirmed at or above this, even if the score
    # otherwise crossed its threshold - the risk penalty in overall_score
    # is proportional, not a hard cutoff, so a genuinely risky coin can
    # still cross 70 if its other signals are strong. Real user data:
    # ~27% of a batch of alerts turned out to be already-rugged coins
    # before this gate existed. Decoupled from
    # paper_trading_risk_gate_max even though they currently match -
    # conceptually separate systems. A null (not yet checked) risk_score
    # does NOT block the alert, only a confirmed high one does.
    alert_risk_gate_max: float = 60.0
    # Applied alongside the risk gate above: skip firing an alert if the
    # coin's liquidity is below this, regardless of score - real user
    # feedback showed alerts firing for coins worth fractions of a cent
    # per token with negligible real liquidity, which crossed the score
    # threshold on other signals but weren't meaningful opportunities.
    # Note this is about LIQUIDITY/scale, not price-per-token - a coin can
    # have a tiny price and still be a real, liquid opportunity (huge
    # token supply is normal for meme coins), so this deliberately gates
    # on liquidity_usd, not price_usd.
    alert_min_liquidity_usd: float = 10_000.0
    # When True (the default, per direct user request), suppresses
    # risk-INCREASING alerts specifically, while still allowing
    # risk-decreasing ones and all other alert types through - every other
    # alert type is already inherently a positive signal by construction.
    alert_positive_only: bool = True
    # Genuine delete, not a soft-hide - alerts older than this are removed
    # permanently. 30 days is deliberately generous: real alert history
    # has repeatedly had genuine diagnostic value this session (comparing
    # an alert's timestamp against a fix's deploy time to distinguish
    # stale pre-fix data from a new, real problem) - a short window would
    # destroy exactly that evidence.
    alert_retention_days: int = 30
    alert_cleanup_interval_seconds: int = 86_400  # once a day is plenty for a cleanup task

    # --- YouTube narrative scanning (MODULE 2 extension) ---
    # REAL free tier, confirmed via multiple independent sources: 10,000
    # quota units/day, no card required. search.list costs 100 units/call
    # - the dominant cost here. Budget math: 15 coins/cycle * 100 units =
    # 1,500 units/cycle. Every 4 hours = 6 cycles/day = 9,000 units/day -
    # a real ~10% margin under the 10,000 cap. videos.list (view-count
    # enrichment) costs only 1 unit per up to 50 IDs batched, negligible
    # against the search cost.
    youtube_api_key: str | None = None
    youtube_interval_seconds: int = 14_400  # 4 hours
    youtube_max_coins_per_cycle: int = 15
    youtube_recheck_hours: int = 12
    youtube_search_lookback_days: int = 3  # only search for videos published this recently

    # --- RugCheck.xyz (MODULE 5 extension: Solana-specific risk detection) ---
    # Genuinely optional - see rugcheck.py collector docstring for the real
    # ambiguity found: at least one source states read endpoints work
    # without a key at all. Fills a real, observed gap: GoPlus frequently
    # has no risk data for Solana coins ("No risk data available from
    # GoPlus for this chain/token yet"), and this is used specifically as
    # a fallback for exactly that case, not a full replacement.
    rugcheck_api_key: str | None = None

    # --- Paper Trading (simulated, no real money/wallet) ---
    # Deliberately its own settings, decoupled from ALERT_OVERALL_SCORE_THRESHOLD
    # above even though they currently match - alert thresholds and trading
    # entry rules are conceptually different and may want to diverge later.
    paper_trading_interval_seconds: int = 120
    # Lowered from 70 to 65 at the user's explicit request, specifically
    # to generate real paper trades and empirically observe the actual
    # win rate at a 65 cutoff - given 70 had produced zero real trades
    # across a full overnight run (top scores repeatedly topping out
    # around 58-62), there was no real data to learn from at that bar.
    # This only changes the threshold for opening a SIMULATED trade -
    # every underlying signal, confidence-shrinkage calculation, and
    # manipulation/plausibility check remains completely unchanged.
    # Lowered from 65 to 64 at the user's request - they were seeing 64
    # occasionally on the dashboard, and 65 still hadn't produced any
    # real trades after 5+ days of running. Same principle as the
    # earlier 70->65 change: this only shifts the bar for when the
    # system acts on a score it already computed honestly - every
    # underlying signal, confidence-shrinkage calculation, and
    # manipulation/plausibility check remains completely unchanged.
    paper_trading_entry_score_threshold: float = 64.0
    paper_trading_risk_gate_max: float = 60.0  # skip entry if risk_score >= this
    paper_trading_exit_gain_pct: float = 50.0
    # Real gap found and closed: before these existed, take-profit was the
    # ONLY exit condition anywhere in the code - a losing or flat position
    # would stay "open" forever, meaning win_rate_pct was structurally
    # guaranteed to trend toward 100% regardless of how good or bad the
    # underlying scoring actually was (every trade that COULD close was
    # by definition a win). These two settings make a genuine loss or a
    # stagnant position actually close, so win_rate_pct can finally mean
    # something real.
    # Widened from -20/+25 to a symmetric -50/+50 at the user's request -
    # more tolerance for volatility before exiting either way. Genuine
    # tradeoff worth knowing: at £50 position size, max modeled loss per
    # trade goes from £10 to £25.
    paper_trading_stop_loss_pct: float = -50.0  # close if price drops this % from entry
    paper_trading_max_hold_hours: int = 72  # force-close if still open this long, regardless of price
    paper_trading_position_size_gbp: float = 50.0

    discord_webhook_url: str | None = None

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    alert_email_from: str | None = None
    alert_email_to: str | None = None

    # --- MODULE 3: Wallet Intelligence (EVM chains only - see wallet_service.py) ---
    etherscan_api_key: str | None = None
    wallet_interval_seconds: int = 200
    # Same rationale as risk_recheck_hours - only re-check a coin's wallet
    # data if it's never been checked, or the last check is older than
    # this many hours, rather than blindly re-scanning every EVM coin
    # every cycle regardless of how large that set grows.
    wallet_recheck_hours: int = 6
    # --- Solana wallet intelligence (extends MODULE 3 to the majority
    # chain in most meme-coin datasets, previously EVM-only) ---
    # REAL free tier, confirmed via the actual pricing page (not a search
    # result, which was wrong): 2,500 requests/month, 3 req/sec rate limit.
    # Budget math for these defaults: 1 holders call + 3 PnL calls = 4
    # calls/coin. 5 coins/cycle * 4 calls = 20 calls/cycle. Every 6 hours =
    # 4 cycles/day = 80 calls/day = ~2,400/month - a real, calculable ~4%
    # margin under the 2,500 limit. (Originally set to 4 coins/cycle with
    # a more conservative ~23% margin; retuned upward once the retry-fix
    # and exception-handling-fix were confirmed working in production,
    # since wasted requests on those bugs are no longer eating into the
    # budget the way they were when these numbers were first calculated.)
    solanatracker_api_key: str | None = None
    solana_wallet_interval_seconds: int = 21_600  # 6 hours
    solana_wallet_max_coins_per_cycle: int = 5
    solana_wallet_holders_per_coin: int = 3
    solana_wallet_recheck_hours: int = 12

    # --- Pool migration detector (MODULE 1 extension) ---
    # Real, concrete gap this closes: our discovery/refresh flow only
    # ever looks at the ONE pool address a coin was first found on. A
    # coin discovered early (e.g. on a thin pump.fun-adjacent pool) can
    # have its REAL trading move to a completely different, healthier
    # pool later - something nothing in this system would ever notice,
    # since GeckoTerminal's own /tokens/{address}/pools endpoint (the
    # only way to see this) was never being called for existing coins.
    # Bounded per-cycle like every other collector here, to respect
    # GeckoTerminal's free-tier rate limit.
    pool_migration_interval_seconds: int = 3600
    pool_migration_max_coins_per_cycle: int = 20
    # Only worth re-checking a coin whose CURRENT pool already looks
    # thin/stale - a coin with genuinely healthy liquidity on its
    # current pool has nothing to gain from this check.
    pool_migration_stale_liquidity_threshold_usd: float = 5_000.0
    # A "better" pool must be a MEANINGFUL improvement, not noise -
    # requires the alternate pool's liquidity to be at least this many
    # times the coin's current liquidity before switching.
    pool_migration_improvement_multiple: float = 3.0
    pool_migration_recheck_hours: int = 12
    # A wallet's first 'in' transfer within this many minutes of the coin's
    # launch_time counts toward early_entry_frequency.
    wallet_early_entry_window_minutes: int = 60
    # Wallets with reputation_score >= this are "strong" for the
    # accumulation alert below.
    wallet_strong_reputation_threshold: float = 65.0
    # Fire the accumulation alert when at least this many currently-holding
    # strong wallets bought within the lookback window.
    wallet_accumulation_min_strong_wallets: int = 3
    wallet_accumulation_lookback_hours: int = 24
    # Cooldown before re-firing the same coin's accumulation alert (this
    # condition is a sustained-state check, not a one-time crossing like the
    # score alerts, so it needs a time-based dedup instead).
    wallet_accumulation_alert_cooldown_hours: int = 6

    # Whale entry alert (MODULE 9) - EVM only, uses wallet_transactions +
    # nearest price_history snapshot as a USD-value proxy (see alert_service.py).
    whale_entry_usd_threshold: float = 10_000.0
    whale_entry_lookback_hours: int = 6
    whale_entry_alert_cooldown_hours: int = 6

    # --- MODULE 2: Narrative Scanner (each source independently optional) ---
    # Default is deliberately conservative (2 hours, not 5 minutes) - social
    # posts don't meaningfully change minute-to-minute, and every cycle that
    # finds posts triggers a paid Claude API call per coin. Combined with
    # narrative_max_coins_per_cycle below, this puts a firm, calculable
    # ceiling on monthly spend: worst case is
    # (narrative_max_coins_per_cycle * cycles_per_month * cost_per_call).
    narrative_interval_seconds: int = 7200
    # Hard cap on how many coins get analyzed by Claude per cycle,
    # regardless of how many qualify by liquidity - prioritizes the
    # highest-liquidity coins first. This is what actually bounds your
    # Anthropic bill; the interval above only controls how often that
    # bounded cost repeats.
    narrative_max_coins_per_cycle: int = 15
    # Skip near-zero-liquidity noise to conserve API/LLM budget - only coins
    # above this liquidity get scanned for narrative content at all.
    narrative_min_liquidity_usd: float = 5_000.0
    # Bounded re-check, same pattern as risk/wallet/price-refresh - only
    # coins new or not scanned within this window are checked each cycle,
    # now that free-source scanning is no longer capped by
    # narrative_max_coins_per_cycle (that cap now applies ONLY to the AI
    # analysis step, which is the part that actually costs money).
    narrative_recheck_hours: int = 6
    # Separate from narrative_recheck_hours (which governs how OFTEN a
    # coin gets re-scanned) - this governs how far back to look for
    # ALREADY-COLLECTED posts (e.g. from YouTube, which writes to the
    # same social_posts table but was never being re-read here) when
    # feeding the AI. Found via real production testing: a coin with
    # confirmed real YouTube posts still produced coins_analyzed_by_ai=0
    # every single cycle, because scan_coin only ever looked at posts
    # freshly fetched live within that same function call
    # (Reddit/CryptoPanic/Twitter/Telegram/RSS), never at what already
    # existed in the DB from a separate collector.
    narrative_existing_post_lookback_hours: int = 24
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    reddit_user_agent: str = "NarrativeHunterAI/0.1 (contact: set-your-own)"
    cryptopanic_api_token: str | None = None
    # Free tier: 4 requests/minute. See collectors/lunarcrush.py - this is a
    # bulk snapshot endpoint, so the limit governs page/refresh cadence, not
    # which individual coins get checked.
    lunarcrush_api_key: str | None = None
    twitter_bearer_token: str | None = None

    # --- MODULE 7: Narrative AI ---
    anthropic_api_key: str | None = None
    # Haiku, not Sonnet: this task (scoring a batch of social posts for
    # narrative virality) is a bounded, classification-style job that
    # doesn't need frontier-level reasoning. Confirmed via the real,
    # current pricing page: Haiku 4.5 is $1/$5 per MTok in/out vs
    # Sonnet 5's $2-3/$10-15 - roughly half the cost on both dimensions,
    # directly addressing the cost sensitivity flagged earlier when this
    # integration was first analyzed (before any real key was ever added).
    anthropic_model: str = "claude-haiku-4-5-20251001"
    # Fires once when narrative_score crosses from below to at/above this
    # (mirrors ALERT_OVERALL_SCORE_THRESHOLD's crossing-based dedup pattern).
    alert_narrative_score_threshold: float = 70.0

    # --- MODULE 4: Community Intelligence (analyzes SocialPost data MODULE 2 already collects) ---
    community_interval_seconds: int = 320
    community_lookback_days: int = 7
    alert_community_score_threshold: float = 70.0

    @property
    def discovery_network_list(self) -> list[str]:
        return [n.strip() for n in self.discovery_networks.split(",") if n.strip()]


settings = Settings()
