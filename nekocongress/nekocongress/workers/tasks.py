"""Celery worker tasks for nekocongress."""

from celery import Celery

from nekocongress.config import settings

app = Celery(
    "nekocongress",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@app.task
def recalculate_standings(tournament_id: int) -> dict:
    """Recalculate standings for a tournament after a session closes."""
    # Implemented in P13
    return {"tournament_id": tournament_id, "status": "recalculated"}
