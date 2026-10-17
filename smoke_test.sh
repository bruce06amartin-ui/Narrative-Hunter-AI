#!/usr/bin/env bash
#
# Smoke test for Narrative Hunter AI.
#
# Runs the full pipeline once, in the correct dependency order, against a
# running `docker compose up` instance. Reports which stages ran and what
# data resulted, so you can see at a glance whether the keyless path works
# and which optional integrations are configured.
#
# Usage:
#   ./smoke_test.sh [base_url]
#   (defaults to http://localhost:8000)
#
# This does NOT replace reading the actual response bodies when something
# looks wrong - it's a fast first pass, not a full test suite.

set -uo pipefail

BASE_URL="${1:-http://localhost:8000}"
PASS=0
FAIL=0

color() { printf "\033[%sm%s\033[0m" "$1" "$2"; }
ok()    { color "32" "  ✓ $1"; echo; PASS=$((PASS+1)); }
bad()   { color "31" "  ✗ $1"; echo; FAIL=$((FAIL+1)); }
info()  { color "36" "$1"; echo; }
warn()  { color "33" "  ! $1"; echo; }

# Runs a POST, prints the JSON body compactly, and checks for HTTP success.
run_stage() {
    local label="$1"
    local path="$2"
    local resp status body

    resp=$(curl -s -w "\n%{http_code}" -X POST "${BASE_URL}${path}" --max-time 60)
    status=$(echo "$resp" | tail -n1)
    body=$(echo "$resp" | sed '$d')

    if [[ "$status" -ge 200 && "$status" -lt 300 ]]; then
        ok "$label ($status)"
        echo "    $body" | head -c 300
        echo
    else
        bad "$label ($status)"
        echo "    $body" | head -c 300
        echo
    fi
}

check_get() {
    local label="$1"
    local path="$2"
    local resp status body

    resp=$(curl -s -w "\n%{http_code}" "${BASE_URL}${path}" --max-time 30)
    status=$(echo "$resp" | tail -n1)
    body=$(echo "$resp" | sed '$d')

    if [[ "$status" -eq 200 ]]; then
        ok "$label ($status)"
        echo "    $body" | head -c 300
        echo
    else
        bad "$label ($status)"
    fi
}

echo "=================================================================="
info "Narrative Hunter AI — smoke test against ${BASE_URL}"
echo "=================================================================="

info "\n[0/9] Health check"
check_get "API is reachable" "/api/health"

info "\n[1/9] Discovery (GeckoTerminal + DexScreener — keyless)"
run_stage "Discovery cycle" "/api/discovery/run"

info "\n[2/9] Rug Detection (GoPlus — keyless)"
run_stage "Risk cycle" "/api/risk/run"

info "\n[3/9] Trend Detection (internal — no external API)"
run_stage "Trend cycle" "/api/trend/run"

info "\n[4/9] Wallet Intelligence (Etherscan — needs ETHERSCAN_API_KEY)"
run_stage "Wallet cycle" "/api/wallets/run"

info "\n[5/9] Narrative Scanner (Reddit/CryptoPanic/X optional, Telegram keyless-per-coin)"
run_stage "Narrative cycle" "/api/narratives/run"

info "\n[6/9] Community Intelligence (analyzes narrative data — no separate keys)"
run_stage "Community cycle" "/api/community/run"

info "\n[7/9] Scoring (combines everything above)"
run_stage "Scoring cycle" "/api/scoring/run"

info "\n[8/9] Alerts (checks for threshold crossings — Discord/Telegram/Email optional)"
run_stage "Alert cycle" "/api/alerts/run"

info "\n[9/9] Spot-check resulting data"
check_get "Top opportunities" "/api/coins/top?limit=5"
check_get "High risk coins" "/api/coins/high-risk?limit=5"
check_get "Alert feed" "/api/alerts?limit=5"
check_get "Wallet leaderboard" "/api/wallets?limit=5"

echo ""
echo "=================================================================="
echo "Results: $(color 32 "$PASS passed"), $(color 31 "$FAIL failed")"
echo "=================================================================="
echo ""
echo "Notes:"
echo "  - A 'no_data'/'skipped' result in a stage's body is often EXPECTED"
echo "    on a fresh install (e.g. wallets/narrative need API keys; scoring"
echo "    needs at least one discovery+risk+trend cycle to have run first)."
echo "  - Re-run this a few times a couple minutes apart - some signal"
echo "    (trend, scoring deltas) only appears once there's more than one"
echo "    price_history/historical_scores snapshot to compare against."
echo "  - If a stage returns a 5xx, check 'docker compose logs api' for the"
echo "    traceback - that's a real bug, not a missing-API-key situation."

exit $((FAIL > 0 ? 1 : 0))
