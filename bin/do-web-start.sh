#!/usr/bin/env bash
# bin/do-web-start.sh — entrypoint for the Django web container on DigitalOcean
#
# Runs on every container start:
#   1. Waits for the managed database to accept connections (retries)
#   2. Applies pending migrations (idempotent, safe on every deploy)
#   3. Runs preference validation (non-fatal on failure)
#   4. Copies static files into the shared volume for nginx to serve
#   5. Starts gunicorn with the DO-specific config (TCP bind, UvicornWorker)
set -eo pipefail

cd /tcd
# Ensure tabbycat package is importable (DJANGO_SETTINGS_MODULE=tabbycat.settings)
export PYTHONPATH=/tcd

# ---------------------------------------------------------------------------
# 1. Wait for the managed database to be reachable
#    django-probing is not available, so we use a simple retry loop.
#    DATABASE_URL must be set or this will fail immediately.
# ---------------------------------------------------------------------------
echo "==> Waiting for database..."
MAX_RETRIES=30
for i in $(seq 1 $MAX_RETRIES); do
    if python tabbycat/manage.py inspectdb --noinput > /dev/null 2>&1; then
        echo "    Database is reachable."
        break
    fi
    if [ "$i" -eq "$MAX_RETRIES" ]; then
        echo "    ERROR: database not reachable after ${MAX_RETRIES} attempts."
        exit 1
    fi
    echo "    Not ready yet (attempt $i/$MAX_RETRIES) — retrying in 5s..."
    sleep 5
done

# ---------------------------------------------------------------------------
# 2. Apply pending migrations
# ---------------------------------------------------------------------------
echo "==> Running database migrations..."
python tabbycat/manage.py migrate --noinput

# ---------------------------------------------------------------------------
# 3. Validate dynamic preferences (non-fatal — don't block startup)
# ---------------------------------------------------------------------------
echo "==> Checking preferences..."
python tabbycat/manage.py checkpreferences || true

# ---------------------------------------------------------------------------
# 4. Collect static files into the shared volume
#    The volume is mounted at STATIC_ROOT (/tcd/tabbycat/staticfiles).
#    collectstatic is fast after the first run (only copies changed files).
# ---------------------------------------------------------------------------
echo "==> Collecting static files..."
python tabbycat/manage.py collectstatic --noinput -v 0

# ---------------------------------------------------------------------------
# 5. Start gunicorn (TCP 0.0.0.0:8000, UvicornWorker)
# ---------------------------------------------------------------------------
echo "==> Starting gunicorn (WEB_CONCURRENCY=${WEB_CONCURRENCY:-2})..."
exec gunicorn asgi:application --config ./config/gunicorn-do.conf
