"""Redis pub/sub WebSocket channel manager for nekocongress.

Unlike nekospeech's in-memory ConnectionManager, this uses Redis pub/sub
for multi-replica WebSocket fan-out. When any replica publishes an event,
all replicas receive it and forward to their connected WebSocket clients.

Channel naming:
- congress:chamber:{chamber_id}:events — per-chamber events
- congress:director:{tournament_id}:events — director bird's-eye view

Architecture:
1. WebSocket client connects to a nekocongress replica
2. Replica subscribes to the relevant Redis channel
3. When an event occurs (on any replica), it publishes to Redis
4. All subscribed replicas receive the event
5. Each replica forwards to its locally connected WebSocket clients
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import WebSocket

from nekocongress.config import settings
from nekocongress.websocket.events import EventType, WebSocketEvent

logger = logging.getLogger(__name__)


class RedisChannelManager:
    """Manages WebSocket connections with Redis pub/sub for multi-replica fan-out."""

    def __init__(self) -> None:
        # Local WebSocket connections: channel_name → list of WebSocket
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        # Redis pub/sub subscriber
        self._pubsub: aioredis.client.PubSub | None = None
        self._redis: aioredis.Redis | None = None
        self._listener_task: asyncio.Task | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the Redis pub/sub listener."""
        self._redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
        )
        self._pubsub = self._redis.pubsub()
        self._running = True
        self._listener_task = asyncio.create_task(self._listen())
        logger.info("RedisChannelManager started")

    async def stop(self) -> None:
        """Stop the Redis pub/sub listener and close all connections."""
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.aclose()
        if self._redis:
            await self._redis.aclose()
        logger.info("RedisChannelManager stopped")

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect_chamber(self, websocket: WebSocket, chamber_id: int) -> str:
        """Connect a WebSocket client to a chamber's event channel."""
        channel = self._chamber_channel(chamber_id)
        await websocket.accept()
        self._connections[channel].append(websocket)
        await self._ensure_subscribed(channel)
        logger.info("WS connected to chamber %d (channel=%s, local=%d)",
                     chamber_id, channel, len(self._connections[channel]))
        return channel

    async def connect_director(self, websocket: WebSocket, tournament_id: int) -> str:
        """Connect a director's WebSocket to the tournament-wide channel."""
        channel = self._director_channel(tournament_id)
        await websocket.accept()
        self._connections[channel].append(websocket)
        await self._ensure_subscribed(channel)
        logger.info("WS director connected tournament %d", tournament_id)
        return channel

    async def connect_student(self, websocket: WebSocket, chamber_id: int) -> str:
        """Connect a student's WebSocket (uses same chamber channel)."""
        return await self.connect_chamber(websocket, chamber_id)

    async def connect_scorer(self, websocket: WebSocket, chamber_id: int) -> str:
        """Connect a scorer's WebSocket (uses same chamber channel)."""
        return await self.connect_chamber(websocket, chamber_id)

    def disconnect(self, websocket: WebSocket, channel: str) -> None:
        """Remove a WebSocket from a channel."""
        conns = self._connections.get(channel, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self._connections.pop(channel, None)
        logger.info("WS disconnected from channel %s", channel)

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish_to_chamber(
        self,
        chamber_id: int,
        event_type: EventType,
        session_id: int | None,
        data: dict,
    ) -> None:
        """Publish an event to a chamber's Redis channel.

        This is the primary way to broadcast events. All replicas subscribed
        to this channel will receive the event and forward to their local
        WebSocket clients.
        """
        event = WebSocketEvent(
            event_type=event_type,
            chamber_id=chamber_id,
            session_id=session_id,
            timestamp=datetime.now(timezone.utc),
            data=data,
        )
        channel = self._chamber_channel(chamber_id)
        if self._redis:
            await self._redis.publish(channel, event.model_dump_json())

        # Also publish to director channel for the tournament
        # (tournament_id is in data if provided)
        tournament_id = data.get("tournament_id")
        if tournament_id:
            director_channel = self._director_channel(tournament_id)
            if self._redis:
                await self._redis.publish(director_channel, event.model_dump_json())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _listen(self) -> None:
        """Background task that listens for Redis pub/sub messages."""
        while self._running:
            try:
                if self._pubsub is None or not self._connections:
                    await asyncio.sleep(1)
                    continue
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message and message["type"] == "message":
                    channel = message["channel"]
                    data = message["data"]
                    await self._broadcast_local(channel, data)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in Redis pub/sub listener")
                await asyncio.sleep(1)

    async def _broadcast_local(self, channel: str, data: str) -> None:
        """Forward a Redis message to all locally connected WebSocket clients."""
        conns = self._connections.get(channel, [])
        stale: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(data)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws, channel)

    async def _ensure_subscribed(self, channel: str) -> None:
        """Subscribe to a Redis channel if not already subscribed."""
        if self._pubsub is None:
            return
        await self._pubsub.subscribe(channel)

    @staticmethod
    def _chamber_channel(chamber_id: int) -> str:
        return f"congress:chamber:{chamber_id}:events"

    @staticmethod
    def _director_channel(tournament_id: int) -> str:
        return f"congress:director:{tournament_id}:events"

    def active_connections(self, channel: str) -> int:
        return len(self._connections.get(channel, []))


# Singleton instance
channel_manager = RedisChannelManager()
