#!/bin/bash
# ============================================================================
# cleanup-tenant.sh - Remove a tenant (with safety checks)
# Usage: ./cleanup-tenant.sh <tenant-subdomain> [--force]
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../.env"

TENANT_SUBDOMAIN="${1:-}"
FORCE="${2:-}"

if [[ -z "$TENANT_SUBDOMAIN" ]]; then
    echo "Usage: $0 <tenant-subdomain> [--force]"
    exit 1
fi

TENANT_DIR="${SCRIPT_DIR}/../tenants/${TENANT_SUBDOMAIN}"

if [[ ! -f "${TENANT_DIR}/.env" ]]; then
    echo "Error: Tenant '${TENANT_SUBDOMAIN}' not found"
    exit 1
fi

source "${TENANT_DIR}/.env"

echo "======================================"
echo "DANGER: Tenant Deletion"
echo "======================================"
echo ""
echo "Tenant: ${TENANT_SUBDOMAIN}"
echo "Database: ${TENANT_DB_NAME}"
echo "Tenant ID: ${TENANT_ID}"
echo ""

if [[ "$FORCE" != "--force" ]]; then
    echo "This will PERMANENTLY DELETE:"
    echo "  - Docker stack and containers"
    echo "  - PostgreSQL database and all data"
    echo "  - Media files"
    echo "  - Configuration files"
    echo ""
    read -p "Type the tenant subdomain to confirm: " CONFIRM
    
    if [[ "$CONFIRM" != "$TENANT_SUBDOMAIN" ]]; then
        echo "Aborted."
        exit 1
    fi
    
    echo ""
    echo "Creating backup first..."
    "${SCRIPT_DIR}/backup-tenant.sh" "$TENANT_SUBDOMAIN"
    echo ""
fi

echo "[1/4] Removing Docker stack..."
docker stack rm "tenant-${TENANT_ID}" 2>/dev/null || true

# Wait for services to stop
sleep 10

echo "[2/4] Removing Docker volumes..."
docker volume rm "tenant-${TENANT_ID}_tenant-${TENANT_ID}-media" 2>/dev/null || true

echo "[3/4] Dropping database..."
docker exec -i $(docker ps -q -f name=postgres-master) psql -U "$POSTGRES_ADMIN_USER" -d nekotab_control <<EOF
-- Terminate active connections
SELECT pg_terminate_backend(pid) FROM pg_stat_activity 
WHERE datname = '${TENANT_DB_NAME}' AND pid <> pg_backend_pid();

-- Drop database
DROP DATABASE IF EXISTS ${TENANT_DB_NAME};

-- Drop user
DROP USER IF EXISTS ${TENANT_DB_USER};

-- Update control plane
UPDATE tenants SET status = 'deleted', deleted_at = NOW() WHERE id = '${TENANT_ID}';
EOF

echo "[4/4] Cleaning up config files..."
rm -rf "${TENANT_DIR}"

echo ""
echo "======================================"
echo "✓ Tenant deleted"
echo "======================================"
echo ""
echo "Backup files preserved in: ${SCRIPT_DIR}/../backups/${TENANT_SUBDOMAIN}/"
