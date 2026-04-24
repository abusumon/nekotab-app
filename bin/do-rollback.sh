#!/usr/bin/env bash
# bin/do-rollback.sh — Emergency rollback: DigitalOcean → Heroku
#
# Run this if something goes critically wrong after cutover.
# Heroku must still be running (maintenance mode off) — keep it live for 48-72h.
#
# Usage:
#   export HEROKU_APP=your-heroku-app-name
#   export DO_DOMAIN="nekotab.app"
#   bash bin/do-rollback.sh

set -euo pipefail

HEROKU_APP="${HEROKU_APP:-}"
DO_DOMAIN="${DO_DOMAIN:-nekotab.app}"

for VAR in HEROKU_APP; do
    if [[ -z "${!VAR}" ]]; then
        echo "ERROR: \$$VAR is not set."
        exit 1
    fi
done

echo "============================================================"
echo "  NekoTab ROLLBACK: DigitalOcean → Heroku"
echo "  Heroku app : $HEROKU_APP"
echo "============================================================"
echo ""
echo "This will:"
echo "  1. Confirm Heroku dynos are running"
echo "  2. Prompt you to revert DNS to Heroku addresses"
echo "  3. Enable Heroku maintenance mode, then re-enable once DNS is live"
echo "  4. Print a reminder to investigate the DO failure before retrying"
echo ""
read -r -p "Type 'ROLLBACK' to proceed: " CONFIRM
if [[ "$CONFIRM" != "ROLLBACK" ]]; then
    echo "Aborted."
    exit 0
fi

# ---------------------------------------------------------------------------
# Step 1 — Verify Heroku is running
# ---------------------------------------------------------------------------
echo ""
echo "--> [1/3] Checking Heroku app status..."
heroku ps --app "$HEROKU_APP"

WEB_DYNOS=$(heroku ps:scale --app "$HEROKU_APP" 2>/dev/null | grep -c "web=" || echo 0)
if [[ "$WEB_DYNOS" -eq 0 ]]; then
    echo "    WARNING: Heroku web dynos are scaled to 0. Scaling up..."
    heroku ps:scale web=1 worker=1 --app "$HEROKU_APP"
fi

HEROKU_DOMAIN=$(heroku info --app "$HEROKU_APP" --json 2>/dev/null \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('app',{}).get('web_url','(unknown)'))" 2>/dev/null || echo "(check heroku dashboard)")

echo "    Heroku URL: $HEROKU_DOMAIN"

# ---------------------------------------------------------------------------
# Step 2 — DNS revert instructions
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo "  ACTION REQUIRED: Revert DNS to Heroku"
echo "============================================================"
echo ""
echo "  Update DNS records for $DO_DOMAIN to point to Heroku:"
echo ""
echo "    CNAME  @    $HEROKU_APP.herokuapp.com"
echo "    CNAME  *    $HEROKU_APP.herokuapp.com"
echo "    CNAME  www  $HEROKU_APP.herokuapp.com"
echo ""
echo "  (Or use the custom domain settings in your Heroku dashboard)"
echo ""
read -r -p "DNS reverted? Confirm once propagation looks correct (y/N): " DNS_OK
if [[ "$DNS_OK" != "y" && "$DNS_OK" != "Y" ]]; then
    echo "DNS revert not confirmed. Exiting without further action."
    echo "Ensure DNS points to Heroku before users experience extended downtime."
    exit 0
fi

# ---------------------------------------------------------------------------
# Step 3 — Quick smoke test on Heroku
# ---------------------------------------------------------------------------
echo ""
echo "--> [3/3] Smoke testing Heroku..."
HTTP_CODE=$(curl -sSo /dev/null -w "%{http_code}" --max-time 15 "https://$DO_DOMAIN/" 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" == "200" ]]; then
    echo "    ✓ Heroku is responding (HTTP $HTTP_CODE)"
else
    echo "    ✗ Heroku returned HTTP $HTTP_CODE — check manually at $HEROKU_DOMAIN"
fi

echo ""
echo "============================================================"
echo "  ROLLBACK COMPLETE"
echo "  Production is back on Heroku."
echo ""
echo "  Next steps:"
echo "    1. Investigate the DO deployment failure before retrying"
echo "    2. Check DO logs: ssh nekotab@YOUR_DROPLET 'cd /opt/nekotab && docker compose -f docker-compose.do.yml logs'"
echo "    3. Check Sentry for errors at the time of failure"
echo "    4. Fix the root cause, then re-run bin/do-db-import.sh (dry run)"
echo "       followed by bin/do-cutover.sh"
echo "============================================================"
