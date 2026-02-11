#!/bin/bash
# ============================================================================
# provision-tenant.sh - Provision a new NekoTab tenant
# Usage: ./provision-tenant.sh <tenant-subdomain> [owner-email]
# ============================================================================

set -euo pipefail

# Load environment
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../.env"

TENANT_SUBDOMAIN="${1:-}"
OWNER_EMAIL="${2:-}"

if [[ -z "$TENANT_SUBDOMAIN" ]]; then
    echo "Usage: $0 <tenant-subdomain> [owner-email]"
    echo "Example: $0 acme-debates admin@acme.org"
    exit 1
fi

# Validate subdomain format
if ! [[ "$TENANT_SUBDOMAIN" =~ ^[a-z0-9][a-z0-9-]{2,30}[a-z0-9]$ ]]; then
    echo "Error: Subdomain must be 4-32 chars, lowercase alphanumeric with hyphens"
    exit 1
fi

# Check reserved subdomains
RESERVED="www,admin,api,traefik,grafana,prometheus,mail,ftp,ssh,control"
if [[ ",$RESERVED," == *",$TENANT_SUBDOMAIN,"* ]]; then
    echo "Error: '$TENANT_SUBDOMAIN' is a reserved subdomain"
    exit 1
fi

echo "======================================"
echo "Provisioning tenant: $TENANT_SUBDOMAIN"
echo "======================================"

# Generate unique identifiers
TENANT_ID=$(echo -n "$TENANT_SUBDOMAIN" | sha256sum | head -c 12)
TENANT_SECRET_KEY=$(openssl rand -base64 48 | tr -d '\n/+=')
TENANT_DB_NAME="nekotab_${TENANT_ID}"
TENANT_DB_USER="tenant_${TENANT_ID}"
TENANT_DB_PASSWORD=$(openssl rand -base64 32 | tr -d '\n/+=')

echo "Tenant ID: $TENANT_ID"
echo "Database: $TENANT_DB_NAME"

# ============================================================================
# Step 1: Create PostgreSQL database for tenant
# ============================================================================
echo "[1/5] Creating PostgreSQL database..."

docker exec -i $(docker ps -q -f name=postgres-master) psql -U "$POSTGRES_ADMIN_USER" -d nekotab_control <<EOF
-- Create tenant database user
CREATE USER ${TENANT_DB_USER} WITH PASSWORD '${TENANT_DB_PASSWORD}';

-- Create tenant database
CREATE DATABASE ${TENANT_DB_NAME} OWNER ${TENANT_DB_USER};

-- Revoke all default privileges (isolation)
REVOKE ALL ON DATABASE ${TENANT_DB_NAME} FROM PUBLIC;

-- Grant full access only to tenant user
GRANT ALL PRIVILEGES ON DATABASE ${TENANT_DB_NAME} TO ${TENANT_DB_USER};

-- Record tenant in control plane
INSERT INTO tenants (
    id, subdomain, db_name, db_user, created_at, status, owner_email
) VALUES (
    '${TENANT_ID}',
    '${TENANT_SUBDOMAIN}',
    '${TENANT_DB_NAME}',
    '${TENANT_DB_USER}',
    NOW(),
    'provisioning',
    '${OWNER_EMAIL}'
) ON CONFLICT (subdomain) DO UPDATE SET status = 'reprovisioning';
EOF

echo "✓ Database created"

# ============================================================================
# Step 2: Generate tenant Docker Compose file
# ============================================================================
echo "[2/5] Generating Docker Compose config..."

TENANT_COMPOSE_DIR="${SCRIPT_DIR}/../tenants/${TENANT_SUBDOMAIN}"
mkdir -p "$TENANT_COMPOSE_DIR"

# Replace placeholders in template
sed -e "s/{{TENANT_ID}}/${TENANT_ID}/g" \
    -e "s/{{TENANT_SUBDOMAIN}}/${TENANT_SUBDOMAIN}/g" \
    -e "s/{{TENANT_SECRET_KEY}}/${TENANT_SECRET_KEY}/g" \
    -e "s/{{TENANT_DB_NAME}}/${TENANT_DB_NAME}/g" \
    -e "s/{{TENANT_DB_USER}}/${TENANT_DB_USER}/g" \
    -e "s/{{TENANT_DB_PASSWORD}}/${TENANT_DB_PASSWORD}/g" \
    "${SCRIPT_DIR}/../docker-compose.tenant.yml" > "${TENANT_COMPOSE_DIR}/docker-compose.yml"

# Save credentials securely
cat > "${TENANT_COMPOSE_DIR}/.env" <<EOF
# Tenant: ${TENANT_SUBDOMAIN}
# Generated: $(date -Iseconds)
TENANT_ID=${TENANT_ID}
TENANT_SUBDOMAIN=${TENANT_SUBDOMAIN}
TENANT_DB_NAME=${TENANT_DB_NAME}
TENANT_DB_USER=${TENANT_DB_USER}
TENANT_DB_PASSWORD=${TENANT_DB_PASSWORD}
TENANT_SECRET_KEY=${TENANT_SECRET_KEY}
EOF

chmod 600 "${TENANT_COMPOSE_DIR}/.env"

echo "✓ Compose config generated"

# ============================================================================
# Step 3: Deploy tenant stack
# ============================================================================
echo "[3/5] Deploying tenant stack..."

docker stack deploy \
    -c "${TENANT_COMPOSE_DIR}/docker-compose.yml" \
    --with-registry-auth \
    "tenant-${TENANT_ID}"

echo "✓ Stack deployed"

# ============================================================================
# Step 4: Wait for services and run migrations
# ============================================================================
echo "[4/5] Waiting for services to start..."

MAX_WAIT=120
WAITED=0
while [[ $WAITED -lt $MAX_WAIT ]]; do
    REPLICAS=$(docker service ls --filter "name=tenant-${TENANT_ID}_web" --format '{{.Replicas}}' 2>/dev/null || echo "0/0")
    if [[ "$REPLICAS" == "1/1" ]]; then
        break
    fi
    sleep 5
    WAITED=$((WAITED + 5))
    echo "  Waiting... ($WAITED/${MAX_WAIT}s)"
done

if [[ $WAITED -ge $MAX_WAIT ]]; then
    echo "Warning: Timed out waiting for service. Check logs with:"
    echo "  docker service logs tenant-${TENANT_ID}_web"
fi

# Run Django migrations
echo "Running database migrations..."
CONTAINER_ID=$(docker ps -q -f name="tenant-${TENANT_ID}_web" | head -1)
if [[ -n "$CONTAINER_ID" ]]; then
    docker exec "$CONTAINER_ID" python manage.py migrate --noinput
    echo "✓ Migrations complete"
fi

# ============================================================================
# Step 5: Update control plane status
# ============================================================================
echo "[5/5] Updating control plane..."

docker exec -i $(docker ps -q -f name=postgres-master) psql -U "$POSTGRES_ADMIN_USER" -d nekotab_control <<EOF
UPDATE tenants SET status = 'active', activated_at = NOW() WHERE id = '${TENANT_ID}';
EOF

echo "✓ Tenant activated"

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "======================================"
echo "✓ Tenant provisioned successfully!"
echo "======================================"
echo ""
echo "URL: https://${TENANT_SUBDOMAIN}.${DOMAIN}"
echo "Admin: https://${TENANT_SUBDOMAIN}.${DOMAIN}/admin/"
echo ""
echo "Database: ${TENANT_DB_NAME}"
echo "Tenant ID: ${TENANT_ID}"
echo ""
if [[ -n "$OWNER_EMAIL" ]]; then
    echo "Owner will receive an email at: ${OWNER_EMAIL}"
fi
echo ""
echo "Credentials stored in: ${TENANT_COMPOSE_DIR}/.env"
echo ""
