"""Redis cache helpers for nekocongress."""

import redis.asyncio as redis

from nekocongress.config import settings

redis_pool = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=5,
    retry_on_timeout=True,
)


async def cache_get(key: str) -> str | None:
    return await redis_pool.get(key)


async def cache_set(key: str, value: str, ex: int = 300) -> None:
    await redis_pool.set(key, value, ex=ex)


async def cache_delete(key: str) -> None:
    await redis_pool.delete(key)


def precedence_key(session_id: int) -> str:
    return f"congress:precedence:{session_id}"


def questioner_key(session_id: int) -> str:
    return f"congress:questioner_queue:{session_id}"


def session_state_key(session_id: int) -> str:
    return f"congress:session_state:{session_id}"
