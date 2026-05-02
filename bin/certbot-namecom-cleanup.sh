#!/usr/bin/env sh
set -eu

: "${LETSENCRYPT_BASE_DOMAIN:?LETSENCRYPT_BASE_DOMAIN is required}"
: "${NAMECOM_USERNAME:?NAMECOM_USERNAME is required}"
: "${NAMECOM_API_TOKEN:?NAMECOM_API_TOKEN is required}"

API_BASE="${NAMECOM_API_BASE_URL:-https://api.name.com/v4}"
STATE_DIR="${CERTBOT_STATE_DIR:-/tmp/certbot-namecom}"
TOKEN="${CERTBOT_TOKEN:-}"

if [ -z "$TOKEN" ]; then
  exit 0
fi

STATE_FILE="$STATE_DIR/$TOKEN"
if [ ! -f "$STATE_FILE" ]; then
  exit 0
fi

RECORD_ID=$(sed -n '1p' "$STATE_FILE" | tr -d '\r\n')
if [ -z "$RECORD_ID" ]; then
  rm -f "$STATE_FILE"
  exit 0
fi

python3 - "$API_BASE" "$LETSENCRYPT_BASE_DOMAIN" "$NAMECOM_USERNAME" "$NAMECOM_API_TOKEN" "$RECORD_ID" <<'PY' || true
import base64
import sys
import urllib.request

api_base, base_domain, username, token, record_id = sys.argv[1:]
auth = base64.b64encode(f"{username}:{token}".encode("utf-8")).decode("ascii")
req = urllib.request.Request(
  url=f"{api_base}/domains/{base_domain}/records/{record_id}",
  headers={"Authorization": f"Basic {auth}"},
  method="DELETE",
)
with urllib.request.urlopen(req, timeout=45):
  pass
PY

rm -f "$STATE_FILE"
echo "Deleted Name.com TXT record id=$RECORD_ID"
