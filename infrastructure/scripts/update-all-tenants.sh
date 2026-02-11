#!/bin/bash
# ============================================================================
# update-all-tenants.sh - Rolling update across all tenant instances
# Usage: ./update-all-tenants.sh [image-tag]
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../.env"

IMAGE_TAG="${1:-latest}"
REGISTRY="${REGISTRY_URL:-ghcr.io/abusumon}"
IMAGE="${REGISTRY}/nekotab:${IMAGE_TAG}"

echo "======================================"
echo "Rolling Update: All NekoTab Tenants"
echo "Image: ${IMAGE}"
echo "======================================"

# Pre-flight checks
echo "[Pre-flight] Pulling new image..."
docker pull "$IMAGE"

echo "[Pre-flight] Checking image health..."
docker run --rm "$IMAGE" python -c "import django; print(f'Django {django.VERSION}')"

# Get list of active tenants
TENANT_STACKS=$(docker stack ls --format '{{.Name}}' | grep '^tenant-' || true)
TENANT_COUNT=$(echo "$TENANT_STACKS" | grep -c '^tenant-' || echo 0)

if [[ "$TENANT_COUNT" -eq 0 ]]; then
    echo "No tenant stacks found."
    exit 0
fi

echo "Found ${TENANT_COUNT} tenant stacks to update."
echo ""

# Rolling update with health checks
UPDATED=0
FAILED=0

for STACK in $TENANT_STACKS; do
    TENANT_ID="${STACK#tenant-}"
    echo "----------------------------------------"
    echo "Updating: ${STACK}"
    
    # Update the service image
    if docker service update \
        --image "$IMAGE" \
        --update-parallelism 1 \
        --update-delay 10s \
        --update-failure-action rollback \
        --update-order start-first \
        "${STACK}_web" 2>/dev/null; then
        
        # Wait for healthy state
        MAX_WAIT=120
        WAITED=0
        HEALTHY=false
        
        while [[ $WAITED -lt $MAX_WAIT ]]; do
            STATE=$(docker service ps "${STACK}_web" --format '{{.CurrentState}}' | head -1)
            if [[ "$STATE" == Running* ]]; then
                HEALTHY=true
                break
            fi
            sleep 5
            WAITED=$((WAITED + 5))
        done
        
        if $HEALTHY; then
            # Run migrations
            CONTAINER_ID=$(docker ps -q -f name="${STACK}_web" | head -1)
            if [[ -n "$CONTAINER_ID" ]]; then
                docker exec "$CONTAINER_ID" python manage.py migrate --noinput 2>/dev/null || true
            fi
            echo "✓ Updated successfully"
            ((UPDATED++))
        else
            echo "✗ Health check timeout - rolling back"
            docker service rollback "${STACK}_web" || true
            ((FAILED++))
        fi
    else
        echo "✗ Update failed"
        ((FAILED++))
    fi
    
    # Also update worker if exists
    if docker service ls --filter "name=${STACK}_worker" --format '{{.Name}}' | grep -q .; then
        docker service update --image "$IMAGE" "${STACK}_worker" 2>/dev/null || true
    fi
done

echo ""
echo "======================================"
echo "Update Summary"
echo "======================================"
echo "Total:   ${TENANT_COUNT}"
echo "Updated: ${UPDATED}"
echo "Failed:  ${FAILED}"
echo ""

if [[ "$FAILED" -gt 0 ]]; then
    echo "⚠ Some updates failed. Check logs with:"
    echo "  docker service logs <stack>_web"
    exit 1
fi

echo "✓ All tenants updated successfully!"
