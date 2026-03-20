"""Celery worker tasks for nekocongress."""

import ssl

from celery import Celery

from nekocongress.config import settings

app = Celery(
    "nekocongress",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

_broker_ssl = (
    {"ssl_cert_reqs": ssl.CERT_NONE}
    if settings.celery_broker_url.startswith("rediss://")
    else None
)
_backend_ssl = (
    {"ssl_cert_reqs": ssl.CERT_NONE}
    if settings.celery_result_backend.startswith("rediss://")
    else None
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_use_ssl=_broker_ssl,
    redis_backend_use_ssl=_backend_ssl,
)


@app.task
def recalculate_standings(tournament_id: int) -> dict:
    """Recalculate standings for a tournament after a session closes."""
    # Implemented in P13
    return {"tournament_id": tournament_id, "status": "recalculated"}
