"""Async Redis helpers for caching standings and draw data."""

import json
import logging

import redis.asyncio as redis

from nekospeech.config import settings

logger = logging.getLogger(__name__)

redis_pool = redis.from_url(settings.redis_url, decode_responses=True)


async def cache_get(key: str) -> dict | list | None:
    """Return parsed JSON from Redis, or None on cache miss.

    Returns None (cache miss) if Redis is unavailable, so callers
    fall through to the database without crashing.
    """
    try:
        raw = await redis_pool.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except (redis.ConnectionError, redis.TimeoutError):
        logger.warning("Redis unavailable for cache_get(%s)", key)
        return None


async def cache_set(key: str, value: dict | list, ttl: int = 30) -> None:
    """Store a JSON-serialisable value in Redis with TTL in seconds."""
    try:
        await redis_pool.set(key, json.dumps(value), ex=ttl)
    except (redis.ConnectionError, redis.TimeoutError):
        logger.warning("Redis unavailable for cache_set(%s)", key)


async def cache_delete(key: str) -> None:
    """Invalidate a single cache key."""
    try:
        await redis_pool.delete(key)
    except (redis.ConnectionError, redis.TimeoutError):
        logger.warning("Redis unavailable for cache_delete(%s)", key)


def standings_key(event_id: int, round_number: int | str = "latest") -> str:
    return f"ie:standings:{event_id}:{round_number}"


def draw_key(event_id: int, round_number: int) -> str:
    return f"ie:draw:{event_id}:{round_number}"
