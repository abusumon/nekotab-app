"""WebSocket endpoints — /api/ie/ws/*

Supports two connection modes:
1. Authenticated: ?token=<JWT> — validated on connect, full access
2. Public: no token — read-only (receives broadcasts but cannot send commands)

Expired or invalid tokens cause immediate close (4401/4403).
On reconnect, Vue passes a fresh token via query param.
"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from nekospeech.config import settings
from nekospeech.websocket.manager import connection_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


def _validate_ws_token(token: str) -> dict | None:
    """Validate a JWT token for WebSocket connections. Returns payload or None."""
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


@router.websocket("/api/ie/ws/tournament/{tournament_id}/")
async def tournament_ws(websocket: WebSocket, tournament_id: int):
    # Extract token from query params (?token=...)
    token = websocket.query_params.get("token")

    user_info = None
    if token:
        user_info = _validate_ws_token(token)
        if user_info is None:
            # Token was provided but is invalid/expired — reject
            await websocket.close(code=4401, reason="Invalid or expired token")
            return

    # Accept: authenticated users get full access, public gets read-only broadcasts
    await connection_manager.connect(websocket, tournament_id)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket, tournament_id)
