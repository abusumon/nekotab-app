#!/bin/bash
# ============================================================================
# backup-tenant.sh - Backup a tenant's database and media files
# Usage: ./backup-tenant.sh <tenant-subdomain>
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../.env"

TENANT_SUBDOMAIN="${1:-}"

if [[ -z "$TENANT_SUBDOMAIN" ]]; then
    echo "Usage: $0 <tenant-subdomain>"
    exit 1
fi

TENANT_DIR="${SCRIPT_DIR}/../tenants/${TENANT_SUBDOMAIN}"

if [[ ! -f "${TENANT_DIR}/.env" ]]; then
    echo "Error: Tenant '${TENANT_SUBDOMAIN}' not found"
    exit 1
fi

source "${TENANT_DIR}/.env"

BACKUP_DIR="${SCRIPT_DIR}/../backups/${TENANT_SUBDOMAIN}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/${TENANT_SUBDOMAIN}_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "======================================"
echo "Backing up tenant: ${TENANT_SUBDOMAIN}"
echo "======================================"

# Database backup
echo "[1/3] Dumping database..."

docker exec -i $(docker ps -q -f name=postgres-master) \
    pg_dump -U "$POSTGRES_ADMIN_USER" -d "$TENANT_DB_NAME" \
    --no-owner --no-privileges --clean --if-exists \
    | gzip > "$BACKUP_FILE"

DB_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "✓ Database backup: ${BACKUP_FILE} (${DB_SIZE})"

# Media files backup
echo "[2/3] Backing up media files..."

MEDIA_BACKUP="${BACKUP_DIR}/${TENANT_SUBDOMAIN}_${TIMESTAMP}_media.tar.gz"
CONTAINER_ID=$(docker ps -q -f name="tenant-${TENANT_ID}_web" | head -1)

if [[ -n "$CONTAINER_ID" ]]; then
    docker exec "$CONTAINER_ID" tar czf - -C /tcd/media . 2>/dev/null > "$MEDIA_BACKUP" || true
    MEDIA_SIZE=$(du -h "$MEDIA_BACKUP" | cut -f1)
    echo "✓ Media backup: ${MEDIA_BACKUP} (${MEDIA_SIZE})"
else
    echo "⚠ Container not running, skipping media backup"
fi

# Upload to S3 (if configured)
echo "[3/3] Uploading to S3..."

if [[ -n "${S3_BUCKET:-}" ]] && command -v aws &>/dev/null; then
    aws s3 cp "$BACKUP_FILE" "s3://${S3_BUCKET}/backups/${TENANT_SUBDOMAIN}/" --quiet
    if [[ -f "$MEDIA_BACKUP" ]]; then
        aws s3 cp "$MEDIA_BACKUP" "s3://${S3_BUCKET}/backups/${TENANT_SUBDOMAIN}/" --quiet
    fi
    echo "✓ Uploaded to S3"
else
    echo "⚠ S3 not configured, backup stored locally only"
fi

# Cleanup old backups (keep last 7 days locally)
find "$BACKUP_DIR" -type f -mtime +7 -delete 2>/dev/null || true

echo ""
echo "======================================"
echo "✓ Backup complete"
echo "======================================"
echo "Database: ${BACKUP_FILE}"
[[ -f "$MEDIA_BACKUP" ]] && echo "Media: ${MEDIA_BACKUP}"
