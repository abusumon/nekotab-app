#!/usr/bin/env bash
# bin/do-db-import.sh — Import a Heroku PostgreSQL backup into DO Managed PostgreSQL
#
# Run this LOCALLY (not on the Droplet) to rehearse the database migration.
# Safe to run multiple times — it creates a fresh import database each time.
#
# Prerequisites:
#   brew install heroku postgresql    (macOS)
#   apt install heroku postgresql-client  (Debian/Ubuntu)
#
# Usage:
#   export HEROKU_APP=your-heroku-app-name
#   export DO_DB_URL="postgresql://doadmin:PASSWORD@db-host:25060/defaultdb?sslmode=require"
#   bash bin/do-db-import.sh
#
# For the FINAL production import, pass --production flag:
#   bash bin/do-db-import.sh --production

set -euo pipefail

HEROKU_APP="${HEROKU_APP:-}"
DO_DB_URL="${DO_DB_URL:-}"
PRODUCTION="${1:-}"

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
if [[ -z "$HEROKU_APP" ]]; then
    echo "ERROR: Set HEROKU_APP env var to your Heroku app name."
    exit 1
fi
if [[ -z "$DO_DB_URL" ]]; then
    echo "ERROR: Set DO_DB_URL to the DO Managed PostgreSQL connection string."
    exit 1
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DUMP_FILE="/tmp/heroku_backup_${TIMESTAMP}.dump"

echo "============================================================"
echo "  Heroku → DigitalOcean Database Import"
echo "  Heroku app : $HEROKU_APP"
echo "  Timestamp  : $TIMESTAMP"
if [[ "$PRODUCTION" == "--production" ]]; then
    echo "  Mode       : PRODUCTION (writing to live database)"
else
    echo "  Mode       : DRY RUN / STAGING (safe to re-run)"
fi
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# Step 1 — Create a fresh Heroku database backup
# ---------------------------------------------------------------------------
echo "--> [1/5] Creating Heroku database backup..."
heroku pg:backups:capture --app "$HEROKU_APP"

echo "--> Downloading backup to $DUMP_FILE..."
heroku pg:backups:download --app "$HEROKU_APP" --output "$DUMP_FILE"

DUMP_SIZE=$(du -sh "$DUMP_FILE" | cut -f1)
echo "    Backup size: $DUMP_SIZE"

# ---------------------------------------------------------------------------
# Step 2 — Pre-import record counts from Heroku (for verification)
# ---------------------------------------------------------------------------
echo ""
echo "--> [2/5] Counting records in Heroku database (for post-import verification)..."
HEROKU_DB_URL=$(heroku config:get DATABASE_URL --app "$HEROKU_APP")
HEROKU_TOURNAMENTS=$(psql "$HEROKU_DB_URL" -tAc "SELECT COUNT(*) FROM tournaments_tournament;" 2>/dev/null || echo "N/A")
HEROKU_DEBATES=$(psql "$HEROKU_DB_URL" -tAc "SELECT COUNT(*) FROM draw_debate;" 2>/dev/null || echo "N/A")
HEROKU_BALLOTS=$(psql "$HEROKU_DB_URL" -tAc "SELECT COUNT(*) FROM results_ballotsubmission;" 2>/dev/null || echo "N/A")
echo "    tournaments_tournament : $HEROKU_TOURNAMENTS"
echo "    draw_debate            : $HEROKU_DEBATES"
echo "    results_ballotsubmission : $HEROKU_BALLOTS"

# ---------------------------------------------------------------------------
# Step 3 — Restore into DO Managed PostgreSQL
# ---------------------------------------------------------------------------
echo ""
echo "--> [3/5] Restoring backup into DO Managed PostgreSQL..."
if [[ "$PRODUCTION" == "--production" ]]; then
    # For production import, restore into the default database
    pg_restore --no-acl --no-owner -d "$DO_DB_URL" "$DUMP_FILE"
else
    # For dry runs, restore into a scratch database to avoid touching live data
    STAGING_DB_URL="${DO_DB_URL%/*}/nekotab_import_${TIMESTAMP}"
    # Create the staging database (requires superuser; DO doadmin has this)
    BASE_URL="${DO_DB_URL%/*}/defaultdb?sslmode=require"
    psql "$BASE_URL" -c "CREATE DATABASE nekotab_import_${TIMESTAMP};"
    pg_restore --no-acl --no-owner -d "$STAGING_DB_URL" "$DUMP_FILE"
    echo "    Restored into staging DB: nekotab_import_${TIMESTAMP}"
    echo "    Connect with: psql \"$STAGING_DB_URL\""
    DO_DB_URL="$STAGING_DB_URL"
fi
echo "    Restore complete."

# ---------------------------------------------------------------------------
# Step 4 — Post-import verification (compare record counts)
# ---------------------------------------------------------------------------
echo ""
echo "--> [4/5] Verifying record counts in DO database..."
DO_TOURNAMENTS=$(psql "$DO_DB_URL" -tAc "SELECT COUNT(*) FROM tournaments_tournament;" 2>/dev/null || echo "FAIL")
DO_DEBATES=$(psql "$DO_DB_URL" -tAc "SELECT COUNT(*) FROM draw_debate;" 2>/dev/null || echo "FAIL")
DO_BALLOTS=$(psql "$DO_DB_URL" -tAc "SELECT COUNT(*) FROM results_ballotsubmission;" 2>/dev/null || echo "FAIL")

echo ""
echo "    Table                        Heroku     DO"
echo "    tournaments_tournament       $HEROKU_TOURNAMENTS         $DO_TOURNAMENTS"
echo "    draw_debate                  $HEROKU_DEBATES         $DO_DEBATES"
echo "    results_ballotsubmission     $HEROKU_BALLOTS         $DO_BALLOTS"
echo ""

if [[ "$HEROKU_TOURNAMENTS" != "$DO_TOURNAMENTS" ]] || \
   [[ "$HEROKU_DEBATES" != "$DO_DEBATES" ]] || \
   [[ "$HEROKU_BALLOTS" != "$DO_BALLOTS" ]]; then
    echo "WARNING: Record count mismatch detected!  Investigate before proceeding."
    exit 1
else
    echo "    Record counts match. ✓"
fi

# ---------------------------------------------------------------------------
# Step 5 — Cleanup local dump file
# ---------------------------------------------------------------------------
echo ""
echo "--> [5/5] Cleaning up local dump..."
rm -f "$DUMP_FILE"

echo ""
echo "============================================================"
echo "  Import complete!"
if [[ "$PRODUCTION" != "--production" ]]; then
    echo ""
    echo "  Dry run succeeded. For the real cutover run:"
    echo "    bash bin/do-cutover.sh"
fi
echo "============================================================"
