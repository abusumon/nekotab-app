# NekoTab Multi-Tenant Infrastructure Makefile
# Usage: make <target>

.PHONY: help setup deploy-base provision backup update logs clean

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Load environment
-include .env
export

# Colors
CYAN := \033[0;36m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m

help: ## Show this help
	@echo ""
	@echo "$(CYAN)NekoTab Multi-Tenant Infrastructure$(NC)"
	@echo ""
	@echo "$(GREEN)Available targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""

# =============================================================================
# Setup
# =============================================================================

setup: ## Initial setup - create networks, volumes, configs
	@echo "$(GREEN)Setting up NekoTab infrastructure...$(NC)"
	docker network create --driver overlay --attachable traefik-public 2>/dev/null || true
	docker network create --driver overlay internal 2>/dev/null || true
	mkdir -p tenants backups logs
	chmod +x scripts/*.sh
	@echo "$(GREEN)✓ Setup complete$(NC)"

check-env: ## Verify environment configuration
	@echo "$(GREEN)Checking environment...$(NC)"
	@test -f .env || (echo "$(RED)Error: .env file not found. Copy from .env.example$(NC)" && exit 1)
	@test -n "$$DOMAIN" || (echo "$(RED)Error: DOMAIN not set$(NC)" && exit 1)
	@test -n "$$CONTROL_PLANE_SECRET" || (echo "$(RED)Error: CONTROL_PLANE_SECRET not set$(NC)" && exit 1)
	@echo "$(GREEN)✓ Environment OK$(NC)"

# =============================================================================
# Base Infrastructure
# =============================================================================

deploy-base: check-env ## Deploy base infrastructure (Traefik, Redis, Control Plane)
	@echo "$(GREEN)Deploying base infrastructure...$(NC)"
	docker-compose -f docker-compose.base.yml up -d
	@echo "$(GREEN)✓ Base infrastructure deployed$(NC)"
	@echo ""
	@echo "Services:"
	@echo "  - Traefik: https://traefik.$(DOMAIN)"
	@echo "  - Control Plane: https://api.$(DOMAIN)"
	@echo "  - Grafana: https://grafana.$(DOMAIN)"

stop-base: ## Stop base infrastructure
	docker-compose -f docker-compose.base.yml down

restart-base: stop-base deploy-base ## Restart base infrastructure

# =============================================================================
# Tenant Management
# =============================================================================

provision: ## Provision a new tenant (usage: make provision SUBDOMAIN=acme EMAIL=admin@acme.org)
	@test -n "$(SUBDOMAIN)" || (echo "$(RED)Error: SUBDOMAIN required. Usage: make provision SUBDOMAIN=acme$(NC)" && exit 1)
	@echo "$(GREEN)Provisioning tenant: $(SUBDOMAIN)$(NC)"
	./scripts/provision-tenant.sh "$(SUBDOMAIN)" "$(EMAIL)"

list-tenants: ## List all tenants
	@echo "$(GREEN)Active Tenants:$(NC)"
	@docker stack ls | grep '^tenant-' || echo "No tenants found"

tenant-logs: ## View tenant logs (usage: make tenant-logs SUBDOMAIN=acme)
	@test -n "$(SUBDOMAIN)" || (echo "$(RED)Error: SUBDOMAIN required$(NC)" && exit 1)
	@TENANT_ID=$$(echo -n "$(SUBDOMAIN)" | sha256sum | head -c 12); \
	docker service logs -f --tail 100 "tenant-$${TENANT_ID}_web"

tenant-shell: ## Open shell in tenant container (usage: make tenant-shell SUBDOMAIN=acme)
	@test -n "$(SUBDOMAIN)" || (echo "$(RED)Error: SUBDOMAIN required$(NC)" && exit 1)
	@TENANT_ID=$$(echo -n "$(SUBDOMAIN)" | sha256sum | head -c 12); \
	CONTAINER=$$(docker ps -q -f name="tenant-$${TENANT_ID}_web" | head -1); \
	docker exec -it $$CONTAINER /bin/bash

suspend-tenant: ## Suspend a tenant (usage: make suspend-tenant SUBDOMAIN=acme)
	@test -n "$(SUBDOMAIN)" || (echo "$(RED)Error: SUBDOMAIN required$(NC)" && exit 1)
	@TENANT_ID=$$(echo -n "$(SUBDOMAIN)" | sha256sum | head -c 12); \
	docker service scale "tenant-$${TENANT_ID}_web=0" "tenant-$${TENANT_ID}_worker=0"
	@echo "$(YELLOW)Tenant $(SUBDOMAIN) suspended$(NC)"

resume-tenant: ## Resume a suspended tenant (usage: make resume-tenant SUBDOMAIN=acme)
	@test -n "$(SUBDOMAIN)" || (echo "$(RED)Error: SUBDOMAIN required$(NC)" && exit 1)
	@TENANT_ID=$$(echo -n "$(SUBDOMAIN)" | sha256sum | head -c 12); \
	docker service scale "tenant-$${TENANT_ID}_web=1" "tenant-$${TENANT_ID}_worker=1"
	@echo "$(GREEN)Tenant $(SUBDOMAIN) resumed$(NC)"

delete-tenant: ## Delete a tenant (usage: make delete-tenant SUBDOMAIN=acme)
	@test -n "$(SUBDOMAIN)" || (echo "$(RED)Error: SUBDOMAIN required$(NC)" && exit 1)
	./scripts/cleanup-tenant.sh "$(SUBDOMAIN)"

# =============================================================================
# Backups
# =============================================================================

backup: ## Backup a tenant (usage: make backup SUBDOMAIN=acme)
	@test -n "$(SUBDOMAIN)" || (echo "$(RED)Error: SUBDOMAIN required$(NC)" && exit 1)
	./scripts/backup-tenant.sh "$(SUBDOMAIN)"

backup-all: ## Backup all tenants
	@echo "$(GREEN)Backing up all tenants...$(NC)"
	@for stack in $$(docker stack ls --format '{{.Name}}' | grep '^tenant-'); do \
		TENANT_DIR=$$(find tenants -mindepth 1 -maxdepth 1 -type d | head -1); \
		if [ -n "$$TENANT_DIR" ]; then \
			./scripts/backup-tenant.sh $$(basename $$TENANT_DIR); \
		fi; \
	done
	@echo "$(GREEN)✓ All backups complete$(NC)"

# =============================================================================
# Updates
# =============================================================================

build: ## Build and push NekoTab Docker image
	@echo "$(GREEN)Building NekoTab image...$(NC)"
	docker build -t $(REGISTRY_URL)/nekotab:$(IMAGE_TAG) ..
	docker push $(REGISTRY_URL)/nekotab:$(IMAGE_TAG)
	@echo "$(GREEN)✓ Image pushed: $(REGISTRY_URL)/nekotab:$(IMAGE_TAG)$(NC)"

update-all: ## Rolling update all tenants to latest image
	@echo "$(GREEN)Updating all tenants...$(NC)"
	./scripts/update-all-tenants.sh "$(IMAGE_TAG)"

update-tenant: ## Update a specific tenant (usage: make update-tenant SUBDOMAIN=acme)
	@test -n "$(SUBDOMAIN)" || (echo "$(RED)Error: SUBDOMAIN required$(NC)" && exit 1)
	@TENANT_ID=$$(echo -n "$(SUBDOMAIN)" | sha256sum | head -c 12); \
	docker service update --image $(REGISTRY_URL)/nekotab:$(IMAGE_TAG) "tenant-$${TENANT_ID}_web"; \
	docker service update --image $(REGISTRY_URL)/nekotab:$(IMAGE_TAG) "tenant-$${TENANT_ID}_worker"
	@echo "$(GREEN)✓ Tenant $(SUBDOMAIN) updated$(NC)"

# =============================================================================
# Monitoring
# =============================================================================

logs: ## View logs for all services
	docker-compose -f docker-compose.base.yml logs -f --tail 100

status: ## Show status of all services
	@echo "$(GREEN)Base Services:$(NC)"
	@docker-compose -f docker-compose.base.yml ps
	@echo ""
	@echo "$(GREEN)Tenant Stacks:$(NC)"
	@docker stack ls | grep -E '^tenant-|^NAME'
	@echo ""
	@echo "$(GREEN)All Services:$(NC)"
	@docker service ls

stats: ## Show resource usage
	@echo "$(GREEN)Resource Usage:$(NC)"
	docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# =============================================================================
# Cleanup
# =============================================================================

prune: ## Clean up unused Docker resources
	@echo "$(YELLOW)Cleaning up unused resources...$(NC)"
	docker system prune -f
	docker volume prune -f
	@echo "$(GREEN)✓ Cleanup complete$(NC)"

clean-logs: ## Clean old log files
	find logs -type f -mtime +30 -delete
	find backups -type f -mtime +30 -delete
	@echo "$(GREEN)✓ Old logs cleaned$(NC)"

# =============================================================================
# Development
# =============================================================================

dev: ## Start development environment
	@echo "$(GREEN)Starting development environment...$(NC)"
	docker-compose -f docker-compose.base.yml -f docker-compose.dev.yml up -d

test: ## Run infrastructure tests
	@echo "$(GREEN)Running tests...$(NC)"
	cd control-plane && python -m pytest tests/
