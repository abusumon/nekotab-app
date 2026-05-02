#!/usr/bin/env sh
set -eu

: "${CERTBOT_DOMAIN:?CERTBOT_DOMAIN is required}"
: "${CERTBOT_VALIDATION:?CERTBOT_VALIDATION is required}"
: "${LETSENCRYPT_BASE_DOMAIN:?LETSENCRYPT_BASE_DOMAIN is required}"
: "${NAMECOM_USERNAME:?NAMECOM_USERNAME is required}"
: "${NAMECOM_API_TOKEN:?NAMECOM_API_TOKEN is required}"

API_BASE="${NAMECOM_API_BASE_URL:-https://api.name.com/v4}"
STATE_DIR="${CERTBOT_STATE_DIR:-/tmp/certbot-namecom}"
SLEEP_SECONDS="${NAMECOM_DNS_PROPAGATION_SECONDS:-45}"

mkdir -p "$STATE_DIR"

DOMAIN="$CERTBOT_DOMAIN"
case "$DOMAIN" in
  \*.*)
    DOMAIN="${DOMAIN#*.}"
    ;;
esac

if [ "$DOMAIN" = "$LETSENCRYPT_BASE_DOMAIN" ]; then
  HOST="_acme-challenge"
else
  SUFFIX=".$LETSENCRYPT_BASE_DOMAIN"
  case "$DOMAIN" in
    *"$SUFFIX")
      PREFIX="${DOMAIN%$SUFFIX}"
      HOST="_acme-challenge.$PREFIX"
      ;;
    *)
      echo "Domain '$CERTBOT_DOMAIN' is not under base domain '$LETSENCRYPT_BASE_DOMAIN'" >&2
      exit 1
      ;;
  esac
fi

RESPONSE=$(python3 - "$API_BASE" "$LETSENCRYPT_BASE_DOMAIN" "$NAMECOM_USERNAME" "$NAMECOM_API_TOKEN" "$HOST" "$CERTBOT_VALIDATION" <<'PY'
import base64
import json
import sys
import urllib.request

api_base, base_domain, username, token, host, validation = sys.argv[1:]
payload = json.dumps({
  "host": host,
  "type": "TXT",
  "answer": validation,
  "ttl": 300,
}).encode("utf-8")

auth = base64.b64encode(f"{username}:{token}".encode("utf-8")).decode("ascii")
req = urllib.request.Request(
  url=f"{api_base}/domains/{base_domain}/records",
  data=payload,
  headers={
    "Authorization": f"Basic {auth}",
    "Content-Type": "application/json",
  },
  method="POST",
)

with urllib.request.urlopen(req, timeout=45) as resp:
  print(resp.read().decode("utf-8"))
PY
)

RECORD_ID=$(python3 - "$RESPONSE" <<'PY'
import json
import sys
obj = json.loads(sys.argv[1])
record_id = obj.get("id")
if not record_id:
    raise SystemExit(1)
print(record_id)
PY
)

TOKEN="${CERTBOT_TOKEN:-$RECORD_ID}"
STATE_FILE="$STATE_DIR/$TOKEN"
{
  printf '%s\n' "$RECORD_ID"
  printf '%s\n' "$HOST"
  printf '%s\n' "$CERTBOT_VALIDATION"
} > "$STATE_FILE"

echo "Created Name.com TXT record id=$RECORD_ID host=$HOST"
sleep "$SLEEP_SECONDS"
