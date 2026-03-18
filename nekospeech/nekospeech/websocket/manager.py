"""WebSocket ConnectionManager for broadcasting events to tournament clients.

Stores connections in a dict keyed by tournament_id.
All shared state is in-memory per replica — this is acceptable because
WebSocket connections are sticky to the process that accepted them.
For cross-replica broadcast in a multi-replica deployment, use Redis PubSub
(not implemented in v1; single-replica WS is sufficient for launch).
"""

import logging
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections grouped by tournament_id."""

    def __init__(self):
        self._connections: dict[int, list[WebSocket]] = defaultdict(list)

    async def connect(self, websocket: WebSocket, tournament_id: int) -> None:
        await websocket.accept()
        self._connections[tournament_id].append(websocket)
        logger.info("WS connected: tournament=%d, total=%d", tournament_id, len(self._connections[tournament_id]))

    def disconnect(self, websocket: WebSocket, tournament_id: int) -> None:
        conns = self._connections.get(tournament_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self._connections.pop(tournament_id, None)
        logger.info("WS disconnected: tournament=%d", tournament_id)

    async def broadcast_to_tournament(self, tournament_id: int, message: dict) -> None:
        """Send a JSON message to all clients connected for a tournament."""
        conns = self._connections.get(tournament_id, [])
        stale = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws, tournament_id)

    def active_connections(self, tournament_id: int) -> int:
        return len(self._connections.get(tournament_id, []))


# Singleton instance used across the application
connection_manager = ConnectionManager()
