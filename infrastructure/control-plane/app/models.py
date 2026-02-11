"""
NekoTab Control Plane - Database Models
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, String, DateTime, Text, Enum as SQLEnum, Integer, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()


class TenantStatus(str, Enum):
    PENDING = "pending"
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"
    ERROR = "error"


class Tenant(Base):
    """Represents a provisioned tenant/organization"""
    __tablename__ = "tenants"
    
    id = Column(String(12), primary_key=True)
    subdomain = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=True)
    
    # Owner info
    owner_email = Column(String(255), nullable=True)
    owner_id = Column(String(64), nullable=True)  # External user ID if using SSO
    
    # Database credentials (encrypted in production)
    db_name = Column(String(64), nullable=False)
    db_user = Column(String(64), nullable=False)
    db_password_encrypted = Column(Text, nullable=True)  # Encrypted
    secret_key_encrypted = Column(Text, nullable=True)   # Encrypted
    
    # Status and lifecycle
    status = Column(SQLEnum(TenantStatus), default=TenantStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    activated_at = Column(DateTime, nullable=True)
    suspended_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    
    # Resource limits
    cpu_limit = Column(String(16), default="1.0")
    memory_limit = Column(String(16), default="512M")
    storage_limit_gb = Column(Integer, default=10)
    
    # Usage tracking
    last_activity_at = Column(DateTime, nullable=True)
    tournament_count = Column(Integer, default=0)
    total_requests = Column(Integer, default=0)
    
    # Billing/plan
    plan = Column(String(32), default="free")
    plan_expires_at = Column(DateTime, nullable=True)
    
    # Metadata
    metadata = Column(JSONB, default=dict)
    
    def __repr__(self):
        return f"<Tenant {self.subdomain} ({self.status.value})>"


class ProvisioningLog(Base):
    """Audit log for provisioning operations"""
    __tablename__ = "provisioning_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(12), nullable=False, index=True)
    action = Column(String(32), nullable=False)  # create, update, suspend, delete
    status = Column(String(16), nullable=False)  # started, success, failed
    message = Column(Text, nullable=True)
    details = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    duration_ms = Column(Integer, nullable=True)


class APIKey(Base):
    """API keys for programmatic access"""
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    key_hash = Column(String(128), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    tenant_id = Column(String(12), nullable=True)  # NULL = admin key
    permissions = Column(JSONB, default=list)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
