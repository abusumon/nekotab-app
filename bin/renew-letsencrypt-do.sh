#!/usr/bin/env bash
set -euo pipefail

cd /opt/nekotab

# Always bring nginx back even if renewal fails.
cleanup() {
  docker compose -f docker-compose.do.yml up -d nginx >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker compose -f docker-compose.do.yml stop nginx

docker run --rm -p 80:80 \
  -v /opt/nekotab/letsencrypt:/etc/letsencrypt \
  -v /opt/nekotab/letsencrypt-lib:/var/lib/letsencrypt \
  certbot/certbot renew \
  --standalone \
  --non-interactive \
  --quiet
