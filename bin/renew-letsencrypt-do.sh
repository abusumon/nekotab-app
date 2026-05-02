#!/usr/bin/env bash
set -euo pipefail

cd /opt/nekotab

read_env_value() {
  local key="$1"
  local file=".env"
  if [[ ! -f "$file" ]]; then
    return 1
  fi
  local line
  line="$(grep -m1 -E "^${key}=" "$file" || true)"
  if [[ -z "$line" ]]; then
    return 1
  fi
  printf '%s' "${line#*=}"
}

if [[ -z "${CERT_NAME:-}" ]]; then
  CERT_NAME="$(read_env_value LETSENCRYPT_CERT_NAME || true)"
fi
if [[ -z "${LETSENCRYPT_DOMAINS:-}" ]]; then
  LETSENCRYPT_DOMAINS="$(read_env_value LETSENCRYPT_DOMAINS || true)"
fi
if [[ -z "${LETSENCRYPT_WILDCARD:-}" ]]; then
  LETSENCRYPT_WILDCARD="$(read_env_value LETSENCRYPT_WILDCARD || true)"
fi

if [[ -z "${LETSENCRYPT_EMAIL:-}" ]]; then
  LETSENCRYPT_EMAIL="$(read_env_value LETSENCRYPT_EMAIL || true)"
fi
if [[ -z "${LETSENCRYPT_BASE_DOMAIN:-}" ]]; then
  LETSENCRYPT_BASE_DOMAIN="$(read_env_value LETSENCRYPT_BASE_DOMAIN || true)"
fi
if [[ -z "${NAMECOM_USERNAME:-}" ]]; then
  NAMECOM_USERNAME="$(read_env_value NAMECOM_USERNAME || true)"
fi
if [[ -z "${NAMECOM_API_TOKEN:-}" ]]; then
  NAMECOM_API_TOKEN="$(read_env_value NAMECOM_API_TOKEN || true)"
fi
if [[ -z "${NAMECOM_API_BASE_URL:-}" ]]; then
  NAMECOM_API_BASE_URL="$(read_env_value NAMECOM_API_BASE_URL || true)"
fi
if [[ -z "${NAMECOM_DNS_PROPAGATION_SECONDS:-}" ]]; then
  NAMECOM_DNS_PROPAGATION_SECONDS="$(read_env_value NAMECOM_DNS_PROPAGATION_SECONDS || true)"
fi

CERT_NAME="${CERT_NAME:-nekotab.app}"
LETSENCRYPT_DOMAINS="${LETSENCRYPT_DOMAINS:-nekotab.app,*.nekotab.app}"
LETSENCRYPT_WILDCARD="${LETSENCRYPT_WILDCARD:-false}"

lower() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

NGINX_STOPPED=0

# Always bring nginx back even if renewal fails.
cleanup() {
  if [[ "$NGINX_STOPPED" == "1" ]]; then
    docker compose -f docker-compose.do.yml up -d nginx >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ "$(lower "$LETSENCRYPT_WILDCARD")" == "true" ]]; then
  : "${LETSENCRYPT_BASE_DOMAIN:?LETSENCRYPT_BASE_DOMAIN is required when LETSENCRYPT_WILDCARD=true}"
  : "${NAMECOM_USERNAME:?NAMECOM_USERNAME is required when LETSENCRYPT_WILDCARD=true}"
  : "${NAMECOM_API_TOKEN:?NAMECOM_API_TOKEN is required when LETSENCRYPT_WILDCARD=true}"

  # Convert comma-separated domains to repeated -d flags.
  declare -a DOMAIN_ARGS=()
  IFS=',' read -r -a RAW_DOMAINS <<< "$LETSENCRYPT_DOMAINS"
  for domain in "${RAW_DOMAINS[@]}"; do
    trimmed="$(echo "$domain" | xargs)"
    if [[ -n "$trimmed" ]]; then
      DOMAIN_ARGS+=("-d" "$trimmed")
    fi
  done

  if [[ ${#DOMAIN_ARGS[@]} -eq 0 ]]; then
    echo "No domains parsed from LETSENCRYPT_DOMAINS=$LETSENCRYPT_DOMAINS" >&2
    exit 1
  fi

  declare -a EMAIL_ARGS=()
  if [[ -n "${LETSENCRYPT_EMAIL:-}" ]]; then
    EMAIL_ARGS=(--email "$LETSENCRYPT_EMAIL")
  else
    EMAIL_ARGS=(--register-unsafely-without-email)
  fi

  docker run --rm \
    -v /opt/nekotab/letsencrypt:/etc/letsencrypt \
    -v /opt/nekotab/letsencrypt-lib:/var/lib/letsencrypt \
    -v /opt/nekotab/bin:/opt/nekotab/bin:ro \
    -e LETSENCRYPT_BASE_DOMAIN="$LETSENCRYPT_BASE_DOMAIN" \
    -e NAMECOM_USERNAME="$NAMECOM_USERNAME" \
    -e NAMECOM_API_TOKEN="$NAMECOM_API_TOKEN" \
    -e NAMECOM_API_BASE_URL="$NAMECOM_API_BASE_URL" \
    -e NAMECOM_DNS_PROPAGATION_SECONDS="$NAMECOM_DNS_PROPAGATION_SECONDS" \
    certbot/certbot certonly \
    --non-interactive \
    --agree-tos \
    --manual \
    --preferred-challenges dns \
    --manual-auth-hook /opt/nekotab/bin/certbot-namecom-auth.sh \
    --manual-cleanup-hook /opt/nekotab/bin/certbot-namecom-cleanup.sh \
    --cert-name "$CERT_NAME" \
    --keep-until-expiring \
    "${EMAIL_ARGS[@]}" \
    "${DOMAIN_ARGS[@]}"
else
  docker compose -f docker-compose.do.yml stop nginx
  NGINX_STOPPED=1

  docker run --rm -p 80:80 \
    -v /opt/nekotab/letsencrypt:/etc/letsencrypt \
    -v /opt/nekotab/letsencrypt-lib:/var/lib/letsencrypt \
    certbot/certbot renew \
    --standalone \
    --non-interactive \
    --quiet
fi
