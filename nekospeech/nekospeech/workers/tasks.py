"""Celery tasks for nekospeech.

Primary task: recalculate IE standings after all rooms in a round are confirmed,
write the result to Redis cache, and broadcast via WebSocket.
"""

import asyncio
import json

from celery import Celery

from nekospeech.config import settings

celery_app = Celery(
    "nekospeech",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


def _run_async(coro):
    """Run an async coroutine from a sync Celery worker context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _recalc_standings_async(event_id: int, round_number: int):
    """Async implementation of the standings recalculation."""
    from nekospeech.database import async_session_factory, engine
    from nekospeech.services.cache import cache_set, standings_key
    from nekospeech.services.standings_engine import compute_standings

    async with async_session_factory() as session:
        standings = await compute_standings(session, event_id, round_number)

    standings_data = standings.model_dump(mode="json")

    # Cache both the round-specific and "latest" keys
    await cache_set(standings_key(event_id, round_number), standings_data, ttl=30)
    await cache_set(standings_key(event_id), standings_data, ttl=30)

    # Dispose the connection pool before the event loop closes. asyncpg connections
    # are bound to the event loop that created them. Each Celery task runs inside a
    # fresh event loop via _run_async(); without dispose() the second task gets pool
    # connections attached to a closed loop, causing RuntimeError or silent failures.
    await engine.dispose()

    # NOTE: WebSocket broadcast is NOT done here because the Celery worker runs
    # in a separate process with its own ConnectionManager (zero connections).
    # The confirm_room endpoint broadcasts "standings_updated" from the web process.


@celery_app.task(name="nekospeech.recalc_standings", bind=True, max_retries=3)
def recalc_standings(self, event_id: int, round_number: int):
    """Recalculate standings for an event through the given round.

    This task is enqueued when all rooms in a round are confirmed.
    It computes truncated-rank standings, caches them in Redis,
    and pushes a WebSocket event to connected clients.
    """
    try:
        _run_async(_recalc_standings_async(event_id, round_number))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=5)
