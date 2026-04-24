#!/usr/bin/env bash
# bin/do-cutover.sh — Production cutover: Heroku → DigitalOcean
#
# This script orchestrates the final go-live migration.
# Run it LOCALLY when you are ready to switch production traffic to DO.
#
# Pre-requisites (verify before running):
#   □ Staging deploy on DO is working (all flows manually tested)
#   □ DNS records are prepared (TTL already lowered to 60s ≥ 24h ago)
#   □ Heroku maintenance mode can be toggled via CLI
#   □ DO Managed PostgreSQL is accessible (DO_DB_URL set)
#   □ GitHub Actions deploy-digitalocean.yml has been triggered at least once
#   □ do-db-import.sh dry run passed successfully
#
# Usage:
#   export HEROKU_APP=your-heroku-app-name
#   export DO_DB_URL="postgresql://doadmin:PASSWORD@host:25060/defaultdb?sslmode=require"
#   export DO_DOMAIN="nekotab.app"          # your base domain
#   export DO_LB_IP="your-do-lb-or-droplet-ip"
#   bash bin/do-cutover.sh

set -euo pipefail

HEROKU_APP="${HEROKU_APP:-}"
DO_DB_URL="${DO_DB_URL:-}"
DO_DOMAIN="${DO_DOMAIN:-nekotab.app}"
DO_LB_IP="${DO_LB_IP:-}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DUMP_FILE="/tmp/final_cutover_${TIMESTAMP}.dump"

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
for VAR in HEROKU_APP DO_DB_URL DO_LB_IP; do
    if [[ -z "${!VAR}" ]]; then
        echo "ERROR: \$$VAR is not set."
        exit 1
    fi
done

echo "============================================================"
echo "  NekoTab Production Cutover: Heroku → DigitalOcean"
echo "  Heroku app   : $HEROKU_APP"
echo "  DO domain    : $DO_DOMAIN"
echo "  DO LB / IP   : $DO_LB_IP"
echo "  Timestamp    : $TIMESTAMP"
echo "============================================================"
echo ""
echo "This will:"
echo "  1. Enable Heroku maintenance mode (write freeze)"
echo "  2. Capture a final database backup from Heroku"
echo "  3. Import it into DO Managed PostgreSQL"
echo "  4. Verify record counts match"
echo "  5. Prompt you to switch DNS"
echo "  6. Verify the new site responds correctly"
echo "  7. Disable Heroku maintenance mode (Heroku stays up for rollback)"
echo ""
read -r -p "Type 'CUTOVER' to proceed: " CONFIRM
if [[ "$CONFIRM" != "CUTOVER" ]]; then
    echo "Aborted."
    exit 0
fi

# ---------------------------------------------------------------------------
# Step 1 — Enable Heroku maintenance mode (freeze writes)
# ---------------------------------------------------------------------------
echo ""
echo "--> [1/7] Enabling Heroku maintenance mode..."
heroku maintenance:on --app "$HEROKU_APP"
echo "    Heroku is now in maintenance mode. Users see the maintenance page."

# ---------------------------------------------------------------------------
# Step 2 — Final database backup from Heroku
# ---------------------------------------------------------------------------
echo ""
echo "--> [2/7] Capturing final Heroku database backup..."
heroku pg:backups:capture --app "$HEROKU_APP"
echo "--> Downloading backup to $DUMP_FILE..."
heroku pg:backups:download --app "$HEROKU_APP" --output "$DUMP_FILE"
DUMP_SIZE=$(du -sh "$DUMP_FILE" | cut -f1)
echo "    Backup size: $DUMP_SIZE"

# ---------------------------------------------------------------------------
# Step 3 — Import into DO PostgreSQL
# ---------------------------------------------------------------------------
echo ""
echo "--> [3/7] Importing into DO Managed PostgreSQL..."
pg_restore --no-acl --no-owner -d "$DO_DB_URL" "$DUMP_FILE"
echo "    Import complete."

# ---------------------------------------------------------------------------
# Step 4 — Record count verification
# ---------------------------------------------------------------------------
echo ""
echo "--> [4/7] Verifying record counts..."
HEROKU_DB_URL=$(heroku config:get DATABASE_URL --app "$HEROKU_APP")

for TABLE in tournaments_tournament draw_debate results_ballotsubmission participants_adjudicator; do
    H_COUNT=$(psql "$HEROKU_DB_URL" -tAc "SELECT COUNT(*) FROM $TABLE;" 2>/dev/null || echo "N/A")
    D_COUNT=$(psql "$DO_DB_URL"     -tAc "SELECT COUNT(*) FROM $TABLE;" 2>/dev/null || echo "N/A")
    STATUS="✓"
    [[ "$H_COUNT" != "$D_COUNT" ]] && STATUS="MISMATCH ✗"
    printf "    %-45s  Heroku: %-8s  DO: %-8s  %s\n" "$TABLE" "$H_COUNT" "$D_COUNT" "$STATUS"
done

echo ""
read -r -p "Record counts look correct? (y/N): " COUNT_OK
if [[ "$COUNT_OK" != "y" && "$COUNT_OK" != "Y" ]]; then
    echo "Aborting — record count issue. Running rollback..."
    heroku maintenance:off --app "$HEROKU_APP"
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 5 — DNS switch prompt
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo "  ACTION REQUIRED: Update DNS"
echo "============================================================"
echo ""
echo "  Point the following DNS records to: $DO_LB_IP"
echo "    A  @           $DO_LB_IP"
echo "    A  *           $DO_LB_IP"
echo "    CNAME  www     $DO_DOMAIN"
echo ""
echo "  If your DNS is managed by DigitalOcean (recommended), update at:"
echo "    https://cloud.digitalocean.com/networking/domains"
echo ""
echo "  TTL should already be 60s (lowered 24h ago). Propagation: ~1-2 minutes."
echo ""
read -r -p "DNS updated? Confirm when propagation looks correct (y/N): " DNS_OK
if [[ "$DNS_OK" != "y" && "$DNS_OK" != "Y" ]]; then
    echo "Waiting for DNS confirmation. Heroku maintenance mode is STILL ON."
    echo "Run this script again or update DNS and continue manually."
    exit 0
fi

# ---------------------------------------------------------------------------
# Step 6 — Smoke tests against the new DO deployment
# ---------------------------------------------------------------------------
echo ""
echo "--> [6/7] Running smoke tests on DO deployment..."

BASE_URL="https://$DO_DOMAIN"
CHECKS_PASSED=0
CHECKS_FAILED=0

check_url() {
    local URL="$1"
    local EXPECTED="$2"
    local LABEL="$3"
    HTTP_CODE=$(curl -sSo /dev/null -w "%{http_code}" --max-time 15 "$URL" 2>/dev/null || echo "000")
    if [[ "$HTTP_CODE" == "$EXPECTED" ]]; then
        echo "    ✓ $LABEL ($HTTP_CODE)"
        ((CHECKS_PASSED++))
    else
        echo "    ✗ $LABEL — expected $EXPECTED, got $HTTP_CODE"
        ((CHECKS_FAILED++))
    fi
}

check_url "$BASE_URL/"            "200" "Homepage"
check_url "$BASE_URL/health/"     "200" "Health check"
check_url "$BASE_URL/accounts/login/" "200" "Login page"
check_url "$BASE_URL/api/"        "200" "API root"

echo ""
echo "    Smoke test results: $CHECKS_PASSED passed, $CHECKS_FAILED failed"

if [[ "$CHECKS_FAILED" -gt 0 ]]; then
    echo ""
    echo "WARNING: Some smoke tests failed. Inspect the DO deployment before proceeding."
    echo "Heroku maintenance mode is STILL ON — users cannot access either site."
    echo ""
    read -r -p "Continue anyway? (ONLY if you can fix the issue on DO) (y/N): " FORCE
    if [[ "$FORCE" != "y" && "$FORCE" != "Y" ]]; then
        echo "Running rollback (re-enabling Heroku, DNS must be reverted manually)..."
        heroku maintenance:off --app "$HEROKU_APP"
        echo "Heroku is back online. Revert DNS to Heroku's addresses."
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# Step 7 — Re-enable Heroku (keeps it as a live rollback target for 48-72h)
# ---------------------------------------------------------------------------
echo ""
echo "--> [7/7] Re-enabling Heroku as rollback target..."
heroku maintenance:off --app "$HEROKU_APP"
echo "    Heroku is back online (rollback target for 48-72h)."
echo "    Scale it down to 0 dynos after confirming DO is stable:"
echo "      heroku ps:scale web=0 worker=0 --app $HEROKU_APP"

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
rm -f "$DUMP_FILE"

echo ""
echo "============================================================"
echo "  CUTOVER COMPLETE"
echo "  Production is now serving from DigitalOcean."
echo ""
echo "  Next steps:"
echo "    1. Monitor DO logs for 24h:  ssh nekotab@$DO_LB_IP 'cd /opt/nekotab && docker compose -f docker-compose.do.yml logs -f'"
echo "    2. Check Sentry for new error spikes"
echo "    3. After 48-72h stability, scale Heroku to 0 and cancel addons"
echo "    4. Set up daily billing alerts on DO dashboard"
echo "============================================================"
