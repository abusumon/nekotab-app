"""Configuration for the nekocongress FastAPI service.

All settings are loaded from environment variables with sensible defaults
for local Docker development.

Heroku deployment notes:
- DATABASE_URL is injected by Heroku Postgres (postgres:// scheme).
  We auto-convert to postgresql+asyncpg://.
- REDIS_URL / REDISCLOUD_URL is injected by Heroku Redis addons.
- DJANGO_SECRET_KEY is used for JWT — same key Django uses.
"""

import os
import re
from typing import Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Database (shared Postgres with Django) ---
    database_url: str = "postgresql+asyncpg://NekoTab:NekoTab@db:5432/NekoTab"

    # --- Redis ---
    redis_url: str = "redis://redis:6379/4"

    # --- Celery ---
    celery_broker_url: str = "redis://redis:6379/5"
    celery_result_backend: str = "redis://redis:6379/5"

    # --- JWT (shared secret with Django) ---
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"

    # --- Congress API key (shared with the Django app) ---
    congress_api_key: str = ""

    # --- Service ---
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:8000", "http://localhost:8080"]

    # --- Congress schema ---
    congress_schema: str = "congress_events"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            stripped = v.strip()
            if stripped.startswith("["):
                import json
                return json.loads(stripped)
            return [s.strip() for s in stripped.split(",") if s.strip()]
        return v

    model_config = {"env_prefix": "NEKOCONGRESS_", "env_file": ".env"}

    @model_validator(mode="after")
    def _resolve_heroku_env(self) -> "Settings":
        """Resolve Heroku-injected env vars with automatic scheme conversion."""

        # --- JWT secret: fall back to Django's SECRET_KEY ---
        if not self.jwt_secret_key:
            self.jwt_secret_key = os.environ.get("DJANGO_SECRET_KEY", "")

        # --- Database URL: fall back to DATABASE_URL (Heroku Postgres) ---
        heroku_db = os.environ.get("DATABASE_URL", "")
        if heroku_db and self.database_url == "postgresql+asyncpg://NekoTab:NekoTab@db:5432/NekoTab":
            self.database_url = _convert_db_scheme(heroku_db)

        # --- Redis URL: fall back to REDISCLOUD_URL → REDIS_URL (Heroku Redis) ---
        heroku_redis = (
            os.environ.get("REDISCLOUD_URL")
            or os.environ.get("REDIS_TLS_URL")
            or os.environ.get("REDIS_URL")
            or ""
        )
        if heroku_redis and self.redis_url == "redis://redis:6379/4":
            self.redis_url = heroku_redis
        if heroku_redis and self.celery_broker_url == "redis://redis:6379/5":
            self.celery_broker_url = heroku_redis
        if heroku_redis and self.celery_result_backend == "redis://redis:6379/5":
            self.celery_result_backend = heroku_redis

        if not self.jwt_secret_key:
            raise ValueError(
                "No JWT secret key configured. "
                "Set NEKOCONGRESS_JWT_SECRET_KEY or DJANGO_SECRET_KEY environment variable."
            )

        return self


def _convert_db_scheme(url: str) -> str:
    """Convert Heroku's postgres:// to postgresql+asyncpg://."""
    return re.sub(r"^postgres(ql)?://", "postgresql+asyncpg://", url)


settings = Settings()
