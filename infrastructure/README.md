# NekoTab Multi-Tenant Infrastructure

## Architecture Overview

This infrastructure implements **complete tenant isolation** for NekoTab, ensuring each user/organization has:

- **Dedicated PostgreSQL database** — No shared tables, complete data isolation
- **Dedicated Docker container** — Independent application instance
- **Dedicated subdomain** — `{tenant}.nekotab.app`
- **Resource limits** — CPU and memory caps per tenant
- **SSL certificates** — Auto-provisioned via Let's Encrypt

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           INTERNET / USERS                                   │
└─────────────────────────────────┬────────────────────────────────────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   Traefik Reverse Proxy   │
                    │   (SSL + Routing + LB)    │
                    │   *.nekotab.app → tenant  │
                    └──────┬──────┬──────┬──────┘
                           │      │      │
          ┌────────────────┼──────┼──────┼────────────────┐
          │                │      │      │                │
    ┌─────▼─────┐    ┌─────▼─────┐│┌─────▼─────┐    ┌─────▼─────┐
    │  Tenant A │    │  Tenant B │││  Tenant C │    │  Tenant N │
    │  Django   │    │  Django   │││  Django   │    │  Django   │
    │  Worker   │    │  Worker   │││  Worker   │    │  Worker   │
    └─────┬─────┘    └─────┬─────┘│└─────┬─────┘    └─────┬─────┘
          │                │      │      │                │
    ┌─────▼─────┐    ┌─────▼─────┐│┌─────▼─────┐    ┌─────▼─────┐
    │  Postgres │    │  Postgres │││  Postgres │    │  Postgres │
    │  DB: A    │    │  DB: B    │││  DB: C    │    │  DB: N    │
    └───────────┘    └───────────┘│└───────────┘    └───────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   Shared Redis Cluster    │
                    │   (Session + Channels)    │
                    └───────────────────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │   Control Plane (API)     │
                    │   Tenant Provisioning     │
                    │   Monitoring + Billing    │
                    └───────────────────────────┘
```

## Directory Structure

```
infrastructure/
├── README.md                     # This file
├── control-plane/                # Central management service
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py              # FastAPI control plane
│   │   ├── provisioner.py       # Tenant provisioning logic
│   │   ├── models.py            # Tenant metadata models
│   │   └── config.py
│   └── templates/
│       └── tenant-compose.yml.j2
├── traefik/
│   ├── traefik.yml              # Static config
│   └── dynamic/                 # Dynamic config per tenant
├── postgres/
│   ├── init-scripts/
│   │   └── init-tenant-db.sh
│   └── pg_hba.conf
├── scripts/
│   ├── provision-tenant.sh
│   ├── backup-tenant.sh
│   ├── update-all-tenants.sh
│   └── cleanup-tenant.sh
├── kubernetes/                  # K8s manifests (optional)
│   ├── namespace.yaml
│   ├── tenant-template.yaml
│   └── traefik-ingress.yaml
├── docker-compose.base.yml      # Base services (Traefik, Redis, Control)
├── docker-compose.tenant.yml    # Template for tenant stacks
├── .env.example
└── Makefile
```

## Deployment Options

### Option A: Docker Swarm (Recommended for <1000 tenants)
- Lower operational complexity
- Native Docker Compose compatibility
- Good for VPS deployments (Hetzner, DigitalOcean)
- ~$0.10-0.30 per tenant/month at scale

### Option B: Kubernetes (Recommended for >1000 tenants)
- Auto-scaling with HPA
- Better resource efficiency via bin-packing
- Cloud provider managed options (GKE, EKS, AKS)
- ~$0.05-0.15 per tenant/month at scale

## Quick Start

```bash
# 1. Clone and setup
cd infrastructure
cp .env.example .env
# Edit .env with your domain, secrets, etc.

# 2. Start base services
docker-compose -f docker-compose.base.yml up -d

# 3. Provision your first tenant
./scripts/provision-tenant.sh acme-debates

# 4. Access at https://acme-debates.nekotab.app
```

## Security Model

1. **Network Isolation**: Each tenant in isolated Docker network
2. **Database Isolation**: Separate PostgreSQL database per tenant
3. **Secret Management**: Per-tenant SECRET_KEY and DB credentials
4. **Resource Limits**: CPU/Memory caps prevent noisy neighbors
5. **Subdomain Routing**: Traefik validates tenant exists before routing
6. **RBAC**: Control plane has separate admin authentication

## Cost Estimates (2026)

| Tenants | Infrastructure | Monthly Cost | Per-Tenant |
|---------|---------------|--------------|------------|
| 10      | Single VPS    | $20          | $2.00      |
| 100     | 2-3 VPS       | $100         | $1.00      |
| 1000    | 10 VPS / K8s  | $500         | $0.50      |
| 5000    | K8s Cluster   | $1500        | $0.30      |

## Monitoring

- **Prometheus + Grafana**: Per-tenant metrics
- **Loki**: Centralized logging
- **Uptime Kuma**: Health checks per subdomain
