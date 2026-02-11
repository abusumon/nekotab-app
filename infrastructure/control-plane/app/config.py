"""
NekoTab Control Plane - Configuration
"""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "NekoTab Control Plane"
    debug: bool = False
    
    # Security
    secret_key: str
    api_key: str
    
    # Domain
    domain: str = "nekotab.app"
    
    # Database (control plane metadata)
    database_url: str
    
    # Redis
    redis_url: str = "redis://redis:6379/0"
    
    # Docker
    docker_host: str = "unix:///var/run/docker.sock"
    registry_url: str = "ghcr.io/abusumon"
    image_tag: str = "latest"
    
    # PostgreSQL (for tenant databases)
    postgres_host: str = "postgres-master"
    postgres_port: int = 5432
    postgres_admin_user: str = "nekotab_admin"
    postgres_admin_password: str
    
    # Default tenant resources
    tenant_cpu_limit: str = "1.0"
    tenant_memory_limit: str = "512M"
    tenant_cpu_reservation: str = "0.25"
    tenant_memory_reservation: str = "256M"
    
    # Reserved subdomains
    reserved_subdomains: list[str] = [
        "www", "admin", "api", "control", "traefik",
        "grafana", "prometheus", "mail", "ftp", "ssh",
        "database", "static", "media", "cdn", "assets"
    ]
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
