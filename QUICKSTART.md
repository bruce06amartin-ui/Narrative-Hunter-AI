# Quickstart: validating this for the first time

Nothing in this codebase has been run against a live network — see the
README's "Known limitations" section for why. This doc is the recommended
order to bring it up and find out what actually works, rather than assuming
anything does.

## 1. Bring the stack up

```bash
cp .env.example .env
make build        # or: docker compose up --build -d
```

Check both come up:
- API: http://localhost:8000/docs
- Dashboard: http://localhost:3000

If either fails to start, `make logs` (or `docker compose logs api` /
`docker compose logs frontend`) first — that's a real bug to report, not
a missing-API-key situation.

## 2. Validate the keyless path

Everything below works with **zero API keys** — GeckoTerminal, DexScreener,
and GoPlus Security are all genuinely free. This is the core pipeline, so
it's the highest-value thing to check first:

```bash
make smoke-test
```

This runs discovery → risk → trend → wallets → narrative → community →
scoring → alerts in order and reports pass/fail per stage. On a fresh
install, expect:
- Discovery, Risk, and Trend to return real data (no keys needed).
- Wallets/Narrative to report `skipped` or `no_data` (expected — no keys yet).
- Scoring to run but produce low-confidence scores until a couple of
  discovery/risk/trend cycles have accumulated history.

Run it 2-3 times, a few minutes apart, to let `price_history` accumulate
enough snapshots for trend detection's 15min/1h windows to populate.

## 3. Add API keys one at a time

Add each to `.env`, restart (`docker compose restart api worker beat`),
then re-run the corresponding smoke-test stage in isolation:

1. **`ETHERSCAN_API_KEY`** (free, https://etherscan.io/apis) →
   `curl -X POST localhost:8000/api/wallets/run`
2. **`ANTHROPIC_API_KEY`** — the one worth watching most closely; the
   JSON-parsing contract in `narrative_ai_service.py` has never been
   exercised against a live response →
   `curl -X POST localhost:8000/api/narratives/run` (also needs at least
   one of Reddit/CryptoPanic/X below, or a coin with a Telegram handle)
3. Reddit / CryptoPanic / X — only if you're willing to go through
   2026's harder access requirements (see each collector's docstring).
   Skip if not; the platform degrades gracefully without them.

## 4. What to actually look at when something breaks

- **5xx response** → real bug. `docker compose logs api` for the traceback.
- **`skipped`/`no_data` in a response body** → expected, not a bug — it
  means an optional integration isn't configured or there's no data yet.
- **Wrong-looking numbers** (scores, risk flags) → check the relevant
  service's docstring first (`risk_service.py`, `wallet_service.py`,
  `trend_service.py`, etc.) — several signals are documented
  approximations, not exact calculations.
- **Frontend build fails** → `cd frontend && npm install && npm run build`
  directly and read the TypeScript errors; nothing here has been run
  through a real Next.js build yet.

## 5. Once it's stable

See the README's "What's left to build" list — Solana wallet indexing is
the highest-value remaining gap, followed by bundle-wallet detection and
Google Trends (the latter genuinely blocked without an official API).
