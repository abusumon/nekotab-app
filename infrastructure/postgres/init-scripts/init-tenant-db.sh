#!/bin/bash
# PostgreSQL initialization script for NekoTab multi-tenant setup
# This runs automatically when the postgres-master container starts

set -e

# Create control plane database and tables
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Extension for UUID generation
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
    
    -- Tenants table (managed by control plane, but initialized here)
    CREATE TABLE IF NOT EXISTS tenants (
        id VARCHAR(12) PRIMARY KEY,
        subdomain VARCHAR(64) UNIQUE NOT NULL,
        name VARCHAR(255),
        owner_email VARCHAR(255),
        owner_id VARCHAR(64),
        db_name VARCHAR(64) NOT NULL,
        db_user VARCHAR(64) NOT NULL,
        db_password_encrypted TEXT,
        secret_key_encrypted TEXT,
        status VARCHAR(20) DEFAULT 'pending' NOT NULL,
        created_at TIMESTAMP DEFAULT NOW() NOT NULL,
        activated_at TIMESTAMP,
        suspended_at TIMESTAMP,
        deleted_at TIMESTAMP,
        cpu_limit VARCHAR(16) DEFAULT '1.0',
        memory_limit VARCHAR(16) DEFAULT '512M',
        storage_limit_gb INTEGER DEFAULT 10,
        last_activity_at TIMESTAMP,
        tournament_count INTEGER DEFAULT 0,
        total_requests INTEGER DEFAULT 0,
        plan VARCHAR(32) DEFAULT 'free',
        plan_expires_at TIMESTAMP,
        metadata JSONB DEFAULT '{}'::jsonb
    );
    
    -- Indexes for common queries
    CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants(status);
    CREATE INDEX IF NOT EXISTS idx_tenants_owner_id ON tenants(owner_id);
    CREATE INDEX IF NOT EXISTS idx_tenants_subdomain ON tenants(subdomain);
    
    -- Provisioning logs table
    CREATE TABLE IF NOT EXISTS provisioning_logs (
        id SERIAL PRIMARY KEY,
        tenant_id VARCHAR(12) NOT NULL,
        action VARCHAR(32) NOT NULL,
        status VARCHAR(16) NOT NULL,
        message TEXT,
        details JSONB,
        created_at TIMESTAMP DEFAULT NOW() NOT NULL,
        duration_ms INTEGER
    );
    
    CREATE INDEX IF NOT EXISTS idx_provisioning_logs_tenant ON provisioning_logs(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_provisioning_logs_created ON provisioning_logs(created_at DESC);
    
    -- API keys table
    CREATE TABLE IF NOT EXISTS api_keys (
        id SERIAL PRIMARY KEY,
        key_hash VARCHAR(128) UNIQUE NOT NULL,
        name VARCHAR(255) NOT NULL,
        tenant_id VARCHAR(12),
        permissions JSONB DEFAULT '[]'::jsonb,
        is_active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT NOW(),
        last_used_at TIMESTAMP,
        expires_at TIMESTAMP
    );
    
    -- Function to update last_activity_at
    CREATE OR REPLACE FUNCTION update_tenant_activity()
    RETURNS TRIGGER AS \$\$
    BEGIN
        UPDATE tenants 
        SET last_activity_at = NOW() 
        WHERE id = NEW.tenant_id;
        RETURN NEW;
    END;
    \$\$ LANGUAGE plpgsql;
    
    RAISE NOTICE 'NekoTab control plane database initialized';
EOSQL

echo "PostgreSQL initialization complete"
