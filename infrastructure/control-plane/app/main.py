"""
NekoTab Control Plane - FastAPI Application
REST API for tenant management and provisioning.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Security, BackgroundTasks, Query
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select, func
import structlog

from .config import get_settings, Settings
from .models import Base, Tenant, TenantStatus, ProvisioningLog
from .provisioner import TenantProvisioner, ProvisioningError

# ============================================================================
# App Setup
# ============================================================================

settings = get_settings()
logger = structlog.get_logger()

app = FastAPI(
    title="NekoTab Control Plane",
    description="Multi-tenant provisioning and management API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database
engine = create_async_engine(
    settings.database_url.replace("postgresql://", "postgresql+asyncpg://"),
    echo=settings.debug,
)
async_session = async_sessionmaker(engine, expire_on_commit=False)


# ============================================================================
# Dependencies
# ============================================================================

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key or api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key


# ============================================================================
# Schemas
# ============================================================================

class TenantCreate(BaseModel):
    subdomain: str = Field(..., min_length=4, max_length=32, pattern=r'^[a-z0-9][a-z0-9-]*[a-z0-9]$')
    name: Optional[str] = None
    owner_email: Optional[EmailStr] = None
    owner_id: Optional[str] = None
    plan: str = "free"
    
    class Config:
        json_schema_extra = {
            "example": {
                "subdomain": "acme-debates",
                "name": "ACME University Debating Society",
                "owner_email": "admin@acme.edu",
                "plan": "free"
            }
        }


class TenantResponse(BaseModel):
    id: str
    subdomain: str
    name: Optional[str]
    status: TenantStatus
    url: str
    created_at: datetime
    activated_at: Optional[datetime]
    plan: str
    tournament_count: int
    
    class Config:
        from_attributes = True


class TenantListResponse(BaseModel):
    tenants: List[TenantResponse]
    total: int
    page: int
    per_page: int


class ProvisionResponse(BaseModel):
    tenant_id: str
    subdomain: str
    url: str
    status: str
    message: str


class StatsResponse(BaseModel):
    total_tenants: int
    active_tenants: int
    suspended_tenants: int
    pending_tenants: int
    total_tournaments: int


# ============================================================================
# Startup/Shutdown
# ============================================================================

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("control_plane_started")


@app.on_event("shutdown")
async def shutdown():
    await engine.dispose()
    logger.info("control_plane_stopped")


# ============================================================================
# Health Endpoints
# ============================================================================

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(select(func.count()).select_from(Tenant))
        return {"status": "ready"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ============================================================================
# Tenant Management Endpoints
# ============================================================================

@app.post(
    "/tenants",
    response_model=ProvisionResponse,
    status_code=202,
    dependencies=[Depends(verify_api_key)]
)
async def create_tenant(
    tenant_data: TenantCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Provision a new tenant.
    
    Creates an isolated environment with:
    - Dedicated PostgreSQL database
    - Docker container with NekoTab
    - SSL-enabled subdomain routing
    
    Returns immediately while provisioning happens in background.
    """
    provisioner = TenantProvisioner(db)
    
    # Validate subdomain
    try:
        provisioner._validate_subdomain(tenant_data.subdomain)
    except ProvisioningError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Check if exists
    existing = await db.execute(
        select(Tenant).where(Tenant.subdomain == tenant_data.subdomain)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Subdomain already exists")
    
    # Start provisioning in background
    async def provision_task():
        async with async_session() as session:
            prov = TenantProvisioner(session)
            try:
                await prov.provision(
                    subdomain=tenant_data.subdomain,
                    owner_email=tenant_data.owner_email,
                    owner_id=tenant_data.owner_id,
                    name=tenant_data.name,
                    plan=tenant_data.plan
                )
            except Exception as e:
                logger.error("background_provision_failed", error=str(e))
    
    background_tasks.add_task(provision_task)
    
    tenant_id = provisioner._generate_tenant_id(tenant_data.subdomain)
    
    return ProvisionResponse(
        tenant_id=tenant_id,
        subdomain=tenant_data.subdomain,
        url=f"https://{tenant_data.subdomain}.{settings.domain}",
        status="provisioning",
        message="Tenant provisioning started. Check status at /tenants/{tenant_id}"
    )


@app.get(
    "/tenants",
    response_model=TenantListResponse,
    dependencies=[Depends(verify_api_key)]
)
async def list_tenants(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    status: Optional[TenantStatus] = None,
    db: AsyncSession = Depends(get_db)
):
    """List all tenants with optional filtering."""
    query = select(Tenant)
    
    if status:
        query = query.where(Tenant.status == status)
    
    # Count
    count_query = select(func.count()).select_from(Tenant)
    if status:
        count_query = count_query.where(Tenant.status == status)
    total = (await db.execute(count_query)).scalar()
    
    # Paginate
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    tenants = result.scalars().all()
    
    return TenantListResponse(
        tenants=[
            TenantResponse(
                id=t.id,
                subdomain=t.subdomain,
                name=t.name,
                status=t.status,
                url=f"https://{t.subdomain}.{settings.domain}",
                created_at=t.created_at,
                activated_at=t.activated_at,
                plan=t.plan,
                tournament_count=t.tournament_count
            )
            for t in tenants
        ],
        total=total,
        page=page,
        per_page=per_page
    )


@app.get(
    "/tenants/{tenant_id}",
    response_model=TenantResponse,
    dependencies=[Depends(verify_api_key)]
)
async def get_tenant(tenant_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific tenant by ID."""
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    return TenantResponse(
        id=tenant.id,
        subdomain=tenant.subdomain,
        name=tenant.name,
        status=tenant.status,
        url=f"https://{tenant.subdomain}.{settings.domain}",
        created_at=tenant.created_at,
        activated_at=tenant.activated_at,
        plan=tenant.plan,
        tournament_count=tenant.tournament_count
    )


@app.post(
    "/tenants/{tenant_id}/suspend",
    dependencies=[Depends(verify_api_key)]
)
async def suspend_tenant(
    tenant_id: str,
    reason: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Suspend a tenant (stops services, keeps data)."""
    provisioner = TenantProvisioner(db)
    
    try:
        await provisioner.suspend(tenant_id, reason)
        return {"status": "suspended", "tenant_id": tenant_id}
    except ProvisioningError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post(
    "/tenants/{tenant_id}/resume",
    dependencies=[Depends(verify_api_key)]
)
async def resume_tenant(tenant_id: str, db: AsyncSession = Depends(get_db)):
    """Resume a suspended tenant."""
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    if tenant.status != TenantStatus.SUSPENDED:
        raise HTTPException(status_code=400, detail="Tenant is not suspended")
    
    # Scale up services
    import docker
    client = docker.from_env()
    
    services = client.services.list(filters={'name': f'tenant-{tenant_id}'})
    for service in services:
        service.update(mode={'Replicated': {'Replicas': 1}})
    
    tenant.status = TenantStatus.ACTIVE
    tenant.suspended_at = None
    await db.commit()
    
    return {"status": "resumed", "tenant_id": tenant_id}


@app.delete(
    "/tenants/{tenant_id}",
    dependencies=[Depends(verify_api_key)]
)
async def delete_tenant(
    tenant_id: str,
    confirm: bool = Query(False),
    db: AsyncSession = Depends(get_db)
):
    """Permanently delete a tenant and all data."""
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Must confirm deletion with ?confirm=true"
        )
    
    provisioner = TenantProvisioner(db)
    
    try:
        await provisioner.delete(tenant_id)
        return {"status": "deleted", "tenant_id": tenant_id}
    except ProvisioningError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Stats Endpoints
# ============================================================================

@app.get("/stats", response_model=StatsResponse, dependencies=[Depends(verify_api_key)])
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get overall platform statistics."""
    result = await db.execute(
        select(
            Tenant.status,
            func.count(Tenant.id),
            func.sum(Tenant.tournament_count)
        ).group_by(Tenant.status)
    )
    
    stats = {row[0]: {"count": row[1], "tournaments": row[2] or 0} for row in result}
    
    return StatsResponse(
        total_tenants=sum(s["count"] for s in stats.values()),
        active_tenants=stats.get(TenantStatus.ACTIVE, {}).get("count", 0),
        suspended_tenants=stats.get(TenantStatus.SUSPENDED, {}).get("count", 0),
        pending_tenants=stats.get(TenantStatus.PENDING, {}).get("count", 0) + 
                        stats.get(TenantStatus.PROVISIONING, {}).get("count", 0),
        total_tournaments=sum(s["tournaments"] for s in stats.values())
    )


# ============================================================================
# Webhook for signup integration
# ============================================================================

class SignupWebhook(BaseModel):
    user_id: str
    email: EmailStr
    subdomain: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "usr_abc123",
                "email": "user@example.com",
                "subdomain": "my-debates"
            }
        }


@app.post("/webhooks/signup", status_code=202)
async def signup_webhook(
    data: SignupWebhook,
    background_tasks: BackgroundTasks,
    api_key: str = Security(api_key_header),
    db: AsyncSession = Depends(get_db)
):
    """
    Webhook called when a new user signs up.
    Automatically provisions a tenant for them.
    """
    if api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    
    # Create tenant in background
    async def provision_task():
        async with async_session() as session:
            prov = TenantProvisioner(session)
            try:
                await prov.provision(
                    subdomain=data.subdomain,
                    owner_email=data.email,
                    owner_id=data.user_id,
                    plan="free"
                )
            except Exception as e:
                logger.error("webhook_provision_failed", error=str(e), user_id=data.user_id)
    
    background_tasks.add_task(provision_task)
    
    return {
        "status": "provisioning",
        "message": f"Tenant {data.subdomain} is being provisioned"
    }
