"""
NekoTab Control Plane - Tenant Provisioner
Handles automated creation, updates, and deletion of tenant infrastructure.
"""
import asyncio
import hashlib
import secrets
import re
from datetime import datetime
from typing import Optional

import docker
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import get_settings
from .models import Tenant, TenantStatus, ProvisioningLog

logger = structlog.get_logger()
settings = get_settings()


class ProvisioningError(Exception):
    """Raised when tenant provisioning fails"""
    pass


class TenantProvisioner:
    """
    Handles the complete lifecycle of tenant infrastructure:
    - Database creation/deletion
    - Docker stack deployment
    - SSL certificate provisioning (via Traefik)
    - Migrations
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.docker_client = docker.from_env()
    
    def _generate_tenant_id(self, subdomain: str) -> str:
        """Generate a unique 12-char tenant ID from subdomain"""
        return hashlib.sha256(subdomain.encode()).hexdigest()[:12]
    
    def _generate_secret_key(self) -> str:
        """Generate a secure Django SECRET_KEY"""
        return secrets.token_urlsafe(48)
    
    def _generate_db_password(self) -> str:
        """Generate a secure database password"""
        return secrets.token_urlsafe(32)
    
    def _validate_subdomain(self, subdomain: str) -> None:
        """Validate subdomain format and availability"""
        # Format check
        pattern = r'^[a-z0-9][a-z0-9-]{2,30}[a-z0-9]$'
        if not re.match(pattern, subdomain):
            raise ProvisioningError(
                "Subdomain must be 4-32 characters, lowercase alphanumeric with hyphens"
            )
        
        # Reserved check
        if subdomain in settings.reserved_subdomains:
            raise ProvisioningError(f"'{subdomain}' is a reserved subdomain")
        
        # Profanity/brand check could go here
    
    async def _log_action(
        self,
        tenant_id: str,
        action: str,
        status: str,
        message: str = None,
        details: dict = None,
        duration_ms: int = None
    ):
        """Record provisioning action to audit log"""
        log_entry = ProvisioningLog(
            tenant_id=tenant_id,
            action=action,
            status=status,
            message=message,
            details=details,
            duration_ms=duration_ms
        )
        self.db.add(log_entry)
        await self.db.commit()
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _create_database(self, tenant: Tenant, db_password: str) -> None:
        """Create isolated PostgreSQL database for tenant"""
        import asyncpg
        
        conn = await asyncpg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            user=settings.postgres_admin_user,
            password=settings.postgres_admin_password,
            database='postgres'
        )
        
        try:
            # Create user
            await conn.execute(f'''
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{tenant.db_user}') THEN
                        CREATE USER {tenant.db_user} WITH PASSWORD '{db_password}';
                    END IF;
                END
                $$;
            ''')
            
            # Create database
            await conn.execute(f'''
                SELECT 'CREATE DATABASE {tenant.db_name} OWNER {tenant.db_user}'
                WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '{tenant.db_name}')
            ''')
            
            # Actually create (can't use parameters for DB name)
            try:
                await conn.execute(f'CREATE DATABASE {tenant.db_name} OWNER {tenant.db_user}')
            except asyncpg.DuplicateDatabaseError:
                pass  # Already exists
            
            # Revoke public access
            await conn.execute(f'REVOKE ALL ON DATABASE {tenant.db_name} FROM PUBLIC')
            await conn.execute(f'GRANT ALL PRIVILEGES ON DATABASE {tenant.db_name} TO {tenant.db_user}')
            
            logger.info("database_created", tenant_id=tenant.id, db_name=tenant.db_name)
            
        finally:
            await conn.close()
    
    async def _deploy_docker_stack(self, tenant: Tenant, db_password: str, secret_key: str) -> None:
        """Deploy the tenant's Docker stack"""
        from jinja2 import Template
        
        # Load template
        template_path = "/app/templates/tenant-compose.yml.j2"
        with open(template_path, 'r') as f:
            template = Template(f.read())
        
        # Render with tenant values
        compose_content = template.render(
            TENANT_ID=tenant.id,
            TENANT_SUBDOMAIN=tenant.subdomain,
            TENANT_SECRET_KEY=secret_key,
            TENANT_DB_NAME=tenant.db_name,
            TENANT_DB_USER=tenant.db_user,
            TENANT_DB_PASSWORD=db_password,
            DOMAIN=settings.domain,
            REGISTRY_URL=settings.registry_url,
            IMAGE_TAG=settings.image_tag,
            TENANT_CPU_LIMIT=tenant.cpu_limit,
            TENANT_MEMORY_LIMIT=tenant.memory_limit,
        )
        
        # Deploy stack using Docker SDK
        # Note: In production, use docker stack deploy via subprocess
        # as the SDK doesn't support Swarm stacks directly
        import subprocess
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write(compose_content)
            compose_file = f.name
        
        try:
            result = subprocess.run(
                ['docker', 'stack', 'deploy', '-c', compose_file, f'tenant-{tenant.id}'],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                raise ProvisioningError(f"Stack deploy failed: {result.stderr}")
            
            logger.info("stack_deployed", tenant_id=tenant.id)
            
        finally:
            import os
            os.unlink(compose_file)
    
    async def _wait_for_healthy(self, tenant: Tenant, timeout: int = 120) -> bool:
        """Wait for tenant services to become healthy"""
        service_name = f"tenant-{tenant.id}_web"
        
        for _ in range(timeout // 5):
            try:
                services = self.docker_client.services.list(filters={'name': service_name})
                if services:
                    service = services[0]
                    tasks = service.tasks()
                    running = [t for t in tasks if t['Status']['State'] == 'running']
                    if running:
                        return True
            except Exception as e:
                logger.warning("health_check_error", error=str(e))
            
            await asyncio.sleep(5)
        
        return False
    
    async def _run_migrations(self, tenant: Tenant) -> None:
        """Run Django migrations for the tenant"""
        import subprocess
        
        # Find the container
        containers = self.docker_client.containers.list(
            filters={'name': f'tenant-{tenant.id}_web'}
        )
        
        if not containers:
            logger.warning("no_container_for_migrations", tenant_id=tenant.id)
            return
        
        container = containers[0]
        
        # Run migrations
        exit_code, output = container.exec_run(
            'python manage.py migrate --noinput',
            demux=True
        )
        
        if exit_code != 0:
            logger.error("migration_failed", tenant_id=tenant.id, output=output)
            raise ProvisioningError(f"Migrations failed: {output}")
        
        logger.info("migrations_complete", tenant_id=tenant.id)
    
    async def provision(
        self,
        subdomain: str,
        owner_email: Optional[str] = None,
        owner_id: Optional[str] = None,
        name: Optional[str] = None,
        plan: str = "free"
    ) -> Tenant:
        """
        Provision a new tenant with complete isolation.
        
        Args:
            subdomain: Unique subdomain for the tenant
            owner_email: Owner's email address
            owner_id: External user ID (for SSO integration)
            name: Display name for the organization
            plan: Pricing plan
        
        Returns:
            The created Tenant object
        
        Raises:
            ProvisioningError: If provisioning fails
        """
        start_time = datetime.utcnow()
        
        # Validate
        self._validate_subdomain(subdomain)
        
        # Check if already exists
        existing = await self.db.execute(
            select(Tenant).where(Tenant.subdomain == subdomain)
        )
        if existing.scalar_one_or_none():
            raise ProvisioningError(f"Subdomain '{subdomain}' already exists")
        
        # Generate credentials
        tenant_id = self._generate_tenant_id(subdomain)
        db_password = self._generate_db_password()
        secret_key = self._generate_secret_key()
        
        # Create tenant record
        tenant = Tenant(
            id=tenant_id,
            subdomain=subdomain,
            name=name or subdomain,
            owner_email=owner_email,
            owner_id=owner_id,
            db_name=f"nekotab_{tenant_id}",
            db_user=f"tenant_{tenant_id}",
            status=TenantStatus.PROVISIONING,
            plan=plan,
            cpu_limit=settings.tenant_cpu_limit,
            memory_limit=settings.tenant_memory_limit,
        )
        
        self.db.add(tenant)
        await self.db.commit()
        
        await self._log_action(tenant_id, "create", "started")
        
        try:
            # Step 1: Create database
            logger.info("provisioning_step", step="database", tenant_id=tenant_id)
            await self._create_database(tenant, db_password)
            
            # Step 2: Deploy Docker stack
            logger.info("provisioning_step", step="deploy", tenant_id=tenant_id)
            await self._deploy_docker_stack(tenant, db_password, secret_key)
            
            # Step 3: Wait for healthy
            logger.info("provisioning_step", step="health_check", tenant_id=tenant_id)
            healthy = await self._wait_for_healthy(tenant)
            
            if not healthy:
                raise ProvisioningError("Service failed to become healthy")
            
            # Step 4: Run migrations
            logger.info("provisioning_step", step="migrations", tenant_id=tenant_id)
            await self._run_migrations(tenant)
            
            # Mark as active
            tenant.status = TenantStatus.ACTIVE
            tenant.activated_at = datetime.utcnow()
            await self.db.commit()
            
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            await self._log_action(
                tenant_id, "create", "success",
                message=f"Tenant provisioned at {subdomain}.{settings.domain}",
                duration_ms=duration_ms
            )
            
            logger.info(
                "tenant_provisioned",
                tenant_id=tenant_id,
                subdomain=subdomain,
                duration_ms=duration_ms
            )
            
            return tenant
            
        except Exception as e:
            # Mark as error
            tenant.status = TenantStatus.ERROR
            await self.db.commit()
            
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            await self._log_action(
                tenant_id, "create", "failed",
                message=str(e),
                duration_ms=duration_ms
            )
            
            logger.error(
                "provisioning_failed",
                tenant_id=tenant_id,
                error=str(e)
            )
            
            raise ProvisioningError(f"Provisioning failed: {e}") from e
    
    async def suspend(self, tenant_id: str, reason: str = None) -> None:
        """Suspend a tenant (stop services but keep data)"""
        tenant = await self.db.get(Tenant, tenant_id)
        if not tenant:
            raise ProvisioningError(f"Tenant {tenant_id} not found")
        
        # Scale down services
        try:
            services = self.docker_client.services.list(
                filters={'name': f'tenant-{tenant_id}'}
            )
            for service in services:
                service.update(mode={'Replicated': {'Replicas': 0}})
        except Exception as e:
            logger.error("suspend_failed", tenant_id=tenant_id, error=str(e))
        
        tenant.status = TenantStatus.SUSPENDED
        tenant.suspended_at = datetime.utcnow()
        tenant.metadata = {**tenant.metadata, 'suspend_reason': reason}
        await self.db.commit()
        
        await self._log_action(tenant_id, "suspend", "success", message=reason)
    
    async def delete(self, tenant_id: str, keep_backup: bool = True) -> None:
        """Permanently delete a tenant and all data"""
        tenant = await self.db.get(Tenant, tenant_id)
        if not tenant:
            raise ProvisioningError(f"Tenant {tenant_id} not found")
        
        await self._log_action(tenant_id, "delete", "started")
        
        try:
            # Remove Docker stack
            import subprocess
            subprocess.run(
                ['docker', 'stack', 'rm', f'tenant-{tenant_id}'],
                capture_output=True,
                timeout=30
            )
            
            # Wait for cleanup
            await asyncio.sleep(10)
            
            # Drop database
            import asyncpg
            conn = await asyncpg.connect(
                host=settings.postgres_host,
                port=settings.postgres_port,
                user=settings.postgres_admin_user,
                password=settings.postgres_admin_password,
                database='postgres'
            )
            
            try:
                # Terminate connections
                await conn.execute(f'''
                    SELECT pg_terminate_backend(pid) 
                    FROM pg_stat_activity 
                    WHERE datname = '{tenant.db_name}' AND pid <> pg_backend_pid()
                ''')
                
                await conn.execute(f'DROP DATABASE IF EXISTS {tenant.db_name}')
                await conn.execute(f'DROP USER IF EXISTS {tenant.db_user}')
            finally:
                await conn.close()
            
            # Mark as deleted (soft delete for audit)
            tenant.status = TenantStatus.DELETED
            tenant.deleted_at = datetime.utcnow()
            await self.db.commit()
            
            await self._log_action(tenant_id, "delete", "success")
            
        except Exception as e:
            await self._log_action(tenant_id, "delete", "failed", message=str(e))
            raise ProvisioningError(f"Deletion failed: {e}") from e
