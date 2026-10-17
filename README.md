# Narrative Hunter AI

A full-stack meme-coin discovery and scoring platform. It continuously discovers new tokens across Solana, Base and Ethereum, scores them on liquidity, price trend, wallet quality, narrative and community signals, filters out manipulated or dead markets, and sends alerts. A paper-trading engine tests the scoring with simulated positions.

**Stack:** FastAPI · Celery (workers + beat) · PostgreSQL · Redis · Next.js / Tailwind / Recharts · Docker Compose · Anthropic Claude (narrative analysis)

**Highlights**
- Weighted multi-signal scoring with an explicit confidence term, so sparse data pulls scores toward neutral instead of inflating them
- Manipulation and dead-market filters (fake liquidity, zero-volume pools, migrated pools)
- Rate-limit-aware pipeline: per-cycle caps, prioritisation by score, Redis task locks
- Paper-trading engine with take-profit, stop-loss and timeout exits
- Live dashboard with auto-refreshing Top 20 opportunities
- Automated test suite (`backend/tests`)

> Experimental research project. Not financial advice. Paper trading only; no real funds are traded.

## Run locally

```bash
cp .env.example .env      # add your own API keys; never commit .env
docker compose up -d --build
```
Dashboard: http://localhost:3000 · API docs: http://localhost:8000/docs

---

# Narrative Hunter AI — MVP (Full 10-Module Spec: Discovery, Narrative Scanner, Wallet Intelligence, Community Intelligence, Rug Detection, Trend Detection, Narrative AI, Scoring, Alerts, Dashboard)

A meme coin intelligence platform. This is a **working implementation of
all 10 spec modules**, running end-to-end: discovery → risk → wallets →
narrative → community → scoring → alerts → dashboard.

That doesn't mean it's *complete* — several modules are honestly "partial":
gated behind API keys that got harder or more expensive to obtain in 2026,
scoped to EVM chains only, or built on reasonable-but-approximate proxies
where the spec asked for something no free/keyless data source can fully
deliver. See [What's implemented](#whats-implemented-vs-pending) below for
exactly what's real, what's approximate, and what's a documented gap in
each module — and the [Known limitations](#known-limitations--next-steps)
section for the full detail on each one.

## What's implemented vs. pending

| Module | Status | Notes |
|---|---|---|
| 1. Coin Discovery Service | ✅ Working | GeckoTerminal `new_pools` (discovery) + DexScreener (enrichment). Now also fetches `telegram_handle`/`twitter_handle` once per coin via GeckoTerminal's token-info endpoint, feeding MODULE 2 |
| 2. Narrative Scanner | ⚠️ Partial | Reddit, CryptoPanic, X (each optional, paid/harder-to-get keys as of 2026), **and now Telegram** — a real `t.me/s/{handle}` scraper, unblocked by the GeckoTerminal handle lookup above. Google Trends remains **not** implemented — no official API exists, and the only alternative (unofficial scraping) is too fragile/ToS-risky to build without live testing |
| 3. Wallet Intelligence | ⚠️ Partial | Real transfer ingestion + reputation scoring via Etherscan V2, **EVM only (eth, base)**. Solana is **not** covered — needs a dedicated indexer this build couldn't verify without live network access |
| 4. Community Intelligence | ⚠️ Partial | Analyzes `social_posts` data MODULE 2 already collected. Spam detection upgraded from exact-text matching to **near-duplicate detection** (word-shingle Jaccard similarity), catching templated-with-edits spam. Still a heuristic, not a real classifier |
| 5. Rug Detection | ⚠️ Partial | GoPlus Security checks, **plus sniper-cluster detection** (many wallets buying within seconds of launch) **and repeat-deployer detection** (same creator address across multiple tracked coins) — both computed from data already collected. Bundle-wallet detection (tracing common funding sources) remains **not** implemented — it needs a separate native-currency transfer call per wallet, which would multiply Etherscan API spend |
| 6. Trend Detection | ✅ Working | **Full velocity/acceleration/decay/momentum model**, computed over 15min/1h/4h price_history comparisons — no longer a simplified proxy |
| 7. Narrative AI | ⚠️ Partial | Real Claude API call (gated on `ANTHROPIC_API_KEY`) — only as good as the posts MODULE 2 found |
| 8. Overall Scoring | ✅ Working | Full spec formula: Liquidity + Trend + Wallet + Narrative + Community weighted-averaged (10:15:20:25:20) + Risk (subtractive penalty) |
| 9. Alerts | ⚠️ Partial | Overall-score, risk-score, narrative-score, community-score threshold crossings, smart-wallet-accumulation, **and now whale entry** (EVM only — estimates USD value from transfer amount × nearest price snapshot) |
| 10. Dashboard | ✅ Working | Next.js + Tailwind + Recharts terminal-style UI. New risk flags (sniper clusters, repeat deployers) and alerts (whale entry) render automatically — the UI treats flag/alert types generically rather than hardcoding a fixed list |

Every `Score` row has a `scoring_notes` field that states exactly which
signals fed into that score, so nothing pretends to be more complete than
it is.

## Architecture

```
GeckoTerminal / DexScreener  →  DiscoveryService  →  Postgres (coins, price_history)
                                                              ↓
                                        GoPlus Security  →  RiskService  →  Postgres (risk_flags, scores.risk_score)
                                                              ↓
                              price_history  →  TrendDetectionService  →  Postgres (scores.trend_score)
                                                              ↓
                        Etherscan (EVM only)  →  WalletIntelligenceService  →  Postgres (wallets, wallet_transactions, scores.wallet_score)
                                                              ↓
   Reddit / CryptoPanic / X / Telegram  →  NarrativeScannerService  →  Claude (NarrativeAIService)  →  Postgres (social_posts, narratives, scores.narrative_score)
                                                              ↓
                    (analyzes social_posts)  →  CommunityIntelligenceService  →  Postgres (communities, scores.community_score)
                                                              ↓
                                                      ScoringService  →  Postgres (scores, historical_scores)
                                                              ↓
                                        AlertService  →  Discord / Telegram / Email  →  Postgres (alerts)
                                                              ↓
                                                      FastAPI REST API (/api/coins, /api/wallets, /api/alerts, ...)
```

Celery Beat triggers discovery every `DISCOVERY_INTERVAL_SECONDS` (default
120s), risk checks every `RISK_INTERVAL_SECONDS` (default 150s), trend
detection every `TREND_INTERVAL_SECONDS` (default 160s), wallet
intelligence every `WALLET_INTERVAL_SECONDS` (default 200s), narrative
scans every `NARRATIVE_INTERVAL_SECONDS` (default 300s), community analysis
every `COMMUNITY_INTERVAL_SECONDS` (default 320s), scoring every
`SCORING_INTERVAL_SECONDS` (default 180s), and alert checks every
`ALERT_INTERVAL_SECONDS` (default 90s) — independently scheduled, but
AlertService dedups against the `alerts` table so it won't refire the same
crossing/change/accumulation condition if its interval happens to run more
often than the cycle that produces the underlying data. You can also
trigger all eight manually via API for local testing — see below.

## Prerequisites

- Docker + Docker Compose
- No API keys needed for discovery/risk/scoring/dashboard — GeckoTerminal,
  DexScreener, and GoPlus Security's public tiers are keyless.
  (Rate limits apply: GeckoTerminal ~30 req/min, DexScreener ~300 req/min. If
  you scale to many chains, you'll want to raise `DISCOVERY_INTERVAL_SECONDS`
  or get a paid tier.)
- **Optional**: a free `ETHERSCAN_API_KEY` (https://etherscan.io/apis) to
  enable MODULE 3 Wallet Intelligence on EVM chains. Without it, wallet
  intelligence is skipped entirely (not faked) and `wallet_score` stays
  `null` for every coin.
- **Optional**: any of `REDDIT_CLIENT_ID`/`SECRET`, `CRYPTOPANIC_API_TOKEN`,
  `TWITTER_BEARER_TOKEN` to enable MODULE 2 Narrative Scanner sources, plus
  `ANTHROPIC_API_KEY` (https://console.anthropic.com) to enable MODULE 7's
  AI analysis of whatever gets collected. None of these have a genuinely
  free/keyless tier left as of 2026 (see the collector docstrings for what
  changed and when) — without them, narrative_score stays `null`.

## Setup

**First time running this? See [QUICKSTART.md](./QUICKSTART.md)** for the
recommended validation order and a `smoke_test.sh` script that exercises
the full pipeline stage-by-stage and reports what actually works.

```bash
cp .env.example .env
docker compose up --build
```

This starts: Postgres, Redis, the FastAPI API (`:8000`), a Celery worker,
Celery beat, and the Next.js dashboard (`:3000`). Tables are created
automatically on API startup (`init_db()` — see the note on Alembic below).

- **Dashboard**: http://localhost:3000
- API root: http://localhost:8000/
- Interactive docs (Swagger UI): http://localhost:8000/docs

## Trying it out

Trigger a discovery + scoring cycle immediately instead of waiting for the
schedule:

```bash
curl -X POST http://localhost:8000/api/discovery/run
curl -X POST http://localhost:8000/api/risk/run
curl -X POST http://localhost:8000/api/trend/run
curl -X POST http://localhost:8000/api/wallets/run
curl -X POST http://localhost:8000/api/narratives/run
curl -X POST http://localhost:8000/api/community/run
curl -X POST http://localhost:8000/api/scoring/run
curl -X POST http://localhost:8000/api/alerts/run
curl http://localhost:8000/api/coins/top
curl http://localhost:8000/api/alerts
curl http://localhost:8000/api/wallets
```

Other endpoints:
- `GET /api/coins` — list coins, filter by `chain`, `min_liquidity`, `search` (symbol/name), sort by `overall_score` / `risk_score` / `liquidity_usd` / `volume_24h_usd` / `launch_time`
- `GET /api/coins/top` / `GET /api/coins/high-risk` — top-ranked / highest-risk active coins
- `GET /api/coins/{id}` — single coin + its current score
- `GET /api/coins/{id}/history` — score time series (for a chart)
- `GET /api/coins/{id}/risk-flags` — individual rug-detection findings for a coin, ranked by severity
- `GET /api/coins/{id}/alerts` — alert history for a coin
- `GET /api/coins/{id}/wallets` — wallets currently holding this coin, ranked by reputation (EVM only)
- `GET /api/coins/{id}/narrative` — current narrative analysis for a coin (404 if none yet)
- `GET /api/coins/{id}/community` — current community health metrics for a coin (404 if none yet)
- `GET /api/coins/{id}/social-posts` — raw collected posts mentioning a coin, ranked by engagement
- `GET /api/alerts` — global alert feed, filter by `severity` or `coin_id`
- `GET /api/wallets` — wallet leaderboard, filter by `chain` / `min_positions`
- `GET /api/wallets/{id}` — single wallet's full reputation breakdown
- `GET /api/health` — DB connectivity check

## Dashboard

Next.js 14 (App Router) + TypeScript + Tailwind + Recharts, in `frontend/`.

- **Homepage** — Top Opportunities, Latest Coins, and High Risk Coins panels,
  plus a live scrolling ticker tape (auto-refreshes every 60s) showing symbol,
  overall score, and 24h change for the top-ranked coins.
- **Coin detail page** (`/coins/[id]`) — price/liquidity stats, a score
  breakdown with Liquidity/Trend/Wallet/Narrative/Community/Risk bars (all
  five spec components now live, none pending), a score-history line chart,
  a full narrative analysis panel (summary, tags, related events), a
  community health panel (growth, engagement, organic-discussion ratio,
  spam proxy), the full list of Rug Detection findings with severity
  coloring, and (EVM chains only) a table of wallets currently holding the coin.
- **Search** — debounced, hits `GET /api/coins?search=`.
- **Alerts page** (`/alerts`) — full alert feed with severity coloring and
  delivery status per alert (which channel it actually went out on, if any).
- **Wallets page** (`/wallets`) — reputation leaderboard across all tracked
  EVM wallets.
- Design direction: dark charcoal terminal aesthetic (Bloomberg-style amber
  as the primary accent, mint/red for gains/risk, monospace for all figures)
  — deliberately following the spec's own "Bloomberg Terminal / Arkham /
  DefiLlama" brief rather than a generic dark-mode default.

Run it outside Docker for faster iteration:

```bash
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

**Note on `NEXT_PUBLIC_API_URL`**: this must be reachable from your
*browser*, not just from inside Docker's network — that's why the default
is `http://localhost:8000` (the host-mapped port) rather than
`http://api:8000` (which only resolves inside the Compose network).

## Configuration

All in `.env` (see `.env.example`):
- `DISCOVERY_NETWORKS` — comma-separated GeckoTerminal network slugs (`solana,eth,base`). GoPlus risk checks support `solana`, `eth`, and `base`; Wallet Intelligence (MODULE 3) supports `eth` and `base` only.
- `DISCOVERY_INTERVAL_SECONDS` / `RISK_INTERVAL_SECONDS` / `TREND_INTERVAL_SECONDS` / `WALLET_INTERVAL_SECONDS` / `NARRATIVE_INTERVAL_SECONDS` / `COMMUNITY_INTERVAL_SECONDS` / `SCORING_INTERVAL_SECONDS`
- `WEIGHT_LIQUIDITY` / `WEIGHT_TREND` / `WEIGHT_WALLET` / `WEIGHT_NARRATIVE` / `WEIGHT_COMMUNITY` — the full spec's weights (10/15/20/25/20 out of 100). `ScoringService` weight-averages whichever of the five are actually available per coin, so these ratios hold even for coins missing some of them.
- `WEIGHT_RISK_PENALTY` — how many points a maximally-risky token (risk_score=100) loses from overall_score (default 0.20, matching the spec's "-20%" exactly)

**Rug Detection extras (no separate keys — analyzes MODULE 3's wallet data and GoPlus's creator_address):**
- `SNIPER_CLUSTER_WINDOW_SECONDS` / `SNIPER_CLUSTER_MIN_WALLETS` — tune the sniper-cluster check
- `REPEAT_DEPLOYER_MIN_OTHER_COINS` — how many other tracked coins from the same creator triggers the flag

**Wallet Intelligence (optional — leave `ETHERSCAN_API_KEY` blank to skip):**
- `ETHERSCAN_API_KEY` — free key from https://etherscan.io/apis (unified V2 API)
- `WALLET_EARLY_ENTRY_WINDOW_MINUTES` — how soon after launch counts as an "early" entry
- `WALLET_STRONG_REPUTATION_THRESHOLD` / `WALLET_ACCUMULATION_MIN_STRONG_WALLETS` / `WALLET_ACCUMULATION_LOOKBACK_HOURS` / `WALLET_ACCUMULATION_ALERT_COOLDOWN_HOURS` — tune the "multiple strong wallets accumulate a token" alert condition
- `WHALE_ENTRY_USD_THRESHOLD` / `WHALE_ENTRY_LOOKBACK_HOURS` / `WHALE_ENTRY_ALERT_COOLDOWN_HOURS` — tune the "large whale enters" alert condition (also EVM-only, same wallet data)

**Narrative Scanner + AI (Reddit/CryptoPanic/X optional; Telegram is keyless but gated per-coin on a discovered handle):**
- `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` / `REDDIT_USER_AGENT` — OAuth2 app credentials (see `app/collectors/reddit.py` for the 2026 access-policy reality)
- `CRYPTOPANIC_API_TOKEN` — crypto news, needs a paid/trial token as of April 2026
- `TWITTER_BEARER_TOKEN` — X posts, pay-per-use only as of Feb 2026
- Telegram needs no config at all — it's driven by whatever `telegram_handle` GeckoTerminal reports for a coin (see `app/collectors/telegram_public.py`)
- `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` — required for MODULE 7's AI analysis step; without it, posts are still collected and stored but never analyzed, so `narrative_score` stays `null`
- `ALERT_NARRATIVE_SCORE_THRESHOLD` — tune the "narrative increases rapidly" alert condition

**Community Intelligence (no separate keys needed — analyzes MODULE 2's data):**
- `COMMUNITY_LOOKBACK_DAYS` — window size for post-volume, engagement, and growth-rate comparisons
- `ALERT_COMMUNITY_SCORE_THRESHOLD` — tune the community-score crossing alert (added beyond the original spec's alert list, for consistency with the narrative/overall-score conditions)

**Alerts (all optional — leave any/all blank to skip that channel):**
- `ALERT_INTERVAL_SECONDS` / `ALERT_OVERALL_SCORE_THRESHOLD` / `ALERT_RISK_SCORE_CHANGE_THRESHOLD`
- `DISCORD_WEBHOOK_URL` — a Discord channel webhook URL
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — from @BotFather + the target chat
- `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `ALERT_EMAIL_FROM` / `ALERT_EMAIL_TO`

Alerts are recorded in the `alerts` table regardless of whether any channel
is configured, so `GET /api/alerts` and the dashboard's Alerts page always
show what would have fired, even before you wire up delivery.

## Development

Run tests (pure scoring-math unit tests, no DB/network required):

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

Run the API locally without Docker (needs local Postgres/Redis, or point
`DATABASE_URL`/`REDIS_URL` at the Dockerized ones):

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Known limitations / next steps

1. **No Alembic migrations yet.** Tables are created via `Base.metadata.create_all()`
   on startup. Fine for an MVP; add Alembic before you need to evolve the
   schema without dropping data.
2. **DexScreener enrichment is best-effort.** Very new pairs sometimes
   aren't indexed by DexScreener yet; discovery still succeeds using
   GeckoTerminal's numbers alone in that case.
3. **Rug Detection (MODULE 5) now covers sniper clusters and repeat
   deployers, but bundle-wallet detection remains unimplemented.** Tracing
   whether multiple holder wallets were funded from a common source address
   before their first buy would need a separate Etherscan `txlist` call
   (native-currency transfers, not just token transfers) per wallet -
   deliberately left out to keep third-party API spend bounded. Sniper-
   cluster detection only works once MODULE 3 has ingested transfer data
   for a coin (it improves over cycles, isn't complete on the first pass).
   Repeat-deployer detection isn't inherently damning - some legitimate
   projects launch many tokens - it's a surfaced signal, not a verdict.
   `risk_score`/`risk_flags` still only reflect what's actually checked;
   treat a low score as "no red flags found," not "guaranteed safe."
4. **GoPlus field parsing was built against their published field reference**
   (https://docs.gopluslabs.io/reference/response-details and
   .../response-detail-1), not guessed — but wasn't exercised against a live
   response in this environment (no outbound network access here). Unit
   tests in `tests/test_goplus_collector.py` use realistic fixtures matching
   that documented schema; run them for real once you have network access,
   and spot-check one live token against the API directly if anything looks off.
5. **Wallet Intelligence (MODULE 3) is EVM-only and approximate by
   necessity.** Read the full docstring at the top of
   `app/services/wallet_service.py` before trusting these numbers — in
   short: Solana isn't covered at all (needs a dedicated indexer this build
   couldn't verify without live network access); "buy"/"sell" are inferred
   from raw ERC20 transfer direction with no DEX router/pool registry to
   filter out non-trade transfers (only the coin's own known `pair_address`
   is excluded); and "ROI" uses the nearest recorded `price_history`
   snapshot as an entry-price proxy, not the actual price at that exact
   block. Etherscan's `tokentx` schema was verified against their live docs
   (see collector docstring), but end-to-end behavior against real data
   wasn't tested here for the same no-network-access reason as GoPlus above.
   The whale-entry alert (MODULE 9) uses this same amount×price-proxy
   approach, so it inherits the same imprecision.
6. **Alerts (MODULE 9) now cover the spec's full five-condition list.**
   Overall-score threshold crossing, risk-score change, smart-wallet-
   accumulation (EVM only), narrative-score threshold crossing, whale entry
   (EVM only, USD-value proxy), and (not in the original spec, added for
   consistency) community-score threshold crossing are all real and live.
   Three different dedup mechanisms are in play depending on the condition
   shape: crossing-based (`_already_alerted`, for one-time threshold
   crossings), cooldown-based (`_recently_alerted`, for sustained-state
   conditions like wallet accumulation), and a size-comparison cooldown for
   whale entry (only re-fires if a strictly larger whale appears within the
   cooldown window) — worth understanding all three before changing any
   `*_INTERVAL_SECONDS` or `*_COOLDOWN_HOURS` value.
7. **Narrative Scanner (MODULE 2) now covers 4 of 5 spec sources.** Reddit,
   CryptoPanic, and X all require paid/hard-to-get keys as of 2026 (read
   the collector docstrings for specifics). Telegram is now real - scraping
   `t.me/s/{handle}` using the handle GeckoTerminal reports for a coin - but
   it's unauthenticated HTML scraping with zero stability guarantee; if
   Telegram changes their markup, `telegram_public.py`'s regex parsing
   breaks silently (logged, not raised) rather than crashing anything.
   Google Trends remains the one source with no implementation at all - no
   official free API exists, and the only alternative (`pytrends`, an
   unofficial scraper) is fragile and ToS-risky at the scale this would
   need. **If zero sources yield anything for a coin, narrative_score stays
   null** - nothing is faked.
8. **Narrative AI (MODULE 7) is only as good as what MODULE 2 collected.**
   A coin with 2 low-quality posts gets a narrative summary built on 2
   low-quality posts - the system prompt instructs the model to reflect
   sparse/weak input with lower scores rather than inventing signal, but
   that's a mitigation, not a guarantee. The Anthropic Messages API call
   itself (`app/services/narrative_ai_service.py`) uses a stable, very
   well-established contract, but wasn't exercised against a live response
   in this build environment for the same no-network-access reason as the
   other integrations above.
9. **Community Intelligence (MODULE 4) is entirely dependent on MODULE 2 —
   it doesn't collect anything itself.** This was a deliberate choice (see
   `app/services/community_service.py` docstring) to avoid a second
   expensive/rate-limited collection pass over largely the same data, but
   it means: zero narrative sources yielding data → zero community data,
   full stop. "Growth" measures post *volume* change, not follower growth.
   "Followers" is Reddit-only (subreddit subscriber count) - X follower
   counts would need a separate per-author API call for every unique
   poster, which wasn't worth the added cost for a proxy signal. Spam
   detection was upgraded from exact-text matching to near-duplicate
   detection (word-shingle Jaccard similarity, catching templated-with-
   edits spam), but it's still a heuristic, not a real classifier -
   bot-generated-but-non-templated spam won't be caught, and the O(n²)
   comparison is capped at 300 posts per coin per cycle for performance.
10. **Frontend wasn't run through a live `next build`/`tsc` in this environment**
    (no Node/network access here to `npm install`). Every file was hand-checked
    for balanced braces/parens and reviewed against the Next.js 14 App Router
    API, but run `npm install && npm run build` yourself before treating it as
    production-ready, and report back if anything doesn't compile. New risk
    flags and alert types (sniper clusters, repeat deployers, whale entry)
    needed zero frontend changes - the UI renders flag/alert types
    generically rather than hardcoding a fixed list.
11. **What's left to build (all 10 spec modules have code; these are the
    honest remaining gaps):**
    - A Solana indexer for MODULE 3 (e.g. integrating Helius's Enhanced
      Transactions API) — would close the biggest remaining gap in Wallet
      Intelligence given Solana is likely the primary meme-coin chain, and
      would also unlock Solana-side sniper-cluster detection in MODULE 5.
    - Bundle-wallet detection for MODULE 5 (common-funding-source tracing).
    - Google Trends for MODULE 2 — genuinely blocked without an official
      API or a scraper stable enough to trust without live testing.
    - A proper spam/bot classifier for MODULE 4 beyond near-duplicate
      text matching, and X follower counts if the extra per-author API
      cost becomes worthwhile.
12. **This platform is an analytics/intelligence tool only.** It does not
    execute trades and makes no promise of investment success, per the
    original spec.
<img width="1918" height="950" alt="image" src="https://github.com/user-attachments/assets/6a9e0b3a-1a1a-43a9-b102-6ecb09641352" />
