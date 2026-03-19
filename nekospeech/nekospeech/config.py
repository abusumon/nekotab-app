"""Configuration for the nekospeech FastAPI service.

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
    # On Heroku, falls back to DATABASE_URL and auto-converts the scheme.
    database_url: str = "postgresql+asyncpg://NekoTab:NekoTab@db:5432/NekoTab"

    # --- Redis ---
    # On Heroku, falls back to REDISCLOUD_URL → REDIS_URL.
    redis_url: str = "redis://redis:6379/2"

    # --- Celery ---
    celery_broker_url: str = "redis://redis:6379/3"
    celery_result_backend: str = "redis://redis:6379/3"

    # --- JWT (shared secret with Django) ---
    # Reads NEKOSPEECH_JWT_SECRET_KEY first, then falls back to DJANGO_SECRET_KEY
    # so both Django and nekospeech validate JWTs with the same key.
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"

    # --- IE API key (shared with the Django app) ---
    ie_api_key: str = ""

    # --- Service ---
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:8000", "http://localhost:8080"]

    # --- Speech events schema ---
    speech_events_schema: str = "speech_events"

    @field_validator('cors_origins', mode='before')
    @classmethod
    def _parse_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            stripped = v.strip()
            # Handle JSON array format: '["https://a.com","https://b.com"]'
            if stripped.startswith('['):
                import json
                return json.loads(stripped)
            # Handle comma-separated format: 'https://a.com,https://b.com'
            return [s.strip() for s in stripped.split(',') if s.strip()]
        return v

    model_config = {"env_prefix": "NEKOSPEECH_", "env_file": ".env"}

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
        if heroku_redis and self.redis_url == "redis://redis:6379/2":
            self.redis_url = heroku_redis
        # Also use as Celery broker/backend if they still have Docker defaults
        if heroku_redis and self.celery_broker_url == "redis://redis:6379/3":
            self.celery_broker_url = heroku_redis
        if heroku_redis and self.celery_result_backend == "redis://redis:6379/3":
            self.celery_result_backend = heroku_redis

        # Fail fast if no JWT secret resolved — silent 401s are worse than a crash
        if not self.jwt_secret_key:
            raise ValueError(
                "No JWT secret key configured. "
                "Set NEKOSPEECH_JWT_SECRET_KEY or DJANGO_SECRET_KEY environment variable."
            )

        return self


def _convert_db_scheme(url: str) -> str:
    """Convert postgres:// or postgresql:// to postgresql+asyncpg://.

    Heroku injects ``postgres://…`` which asyncpg cannot use directly.
    """
    return re.sub(r"^postgres(ql)?://", "postgresql+asyncpg://", url)


settings = Settings()
