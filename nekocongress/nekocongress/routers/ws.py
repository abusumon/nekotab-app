"""WebSocket endpoints — /api/congress/ws/*

Provides real-time event streams for different roles:
- Chamber view (PO/director): all chamber events
- Director bird's-eye: all events across tournament
- Student: chamber events (limited)
- Scorer: chamber events (score-focused)

All connections use Redis pub/sub for multi-replica fan-out.
"""

import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from nekocongress.auth import verify_ws_token
from nekocongress.websocket.redis_manager import channel_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/congress/ws", tags=["websocket"])


@router.websocket("/chamber/{chamber_id}/")
async def ws_chamber(
    websocket: WebSocket,
    chamber_id: int,
):
    """WebSocket for chamber floor view (PO/director).

    Receives all chamber events: speeches, questions, votes, timer ticks.
    Token is passed as query param: ?token=<jwt>
    """
    token = websocket.query_params.get("token")
    if not token or not await _validate_token(token):
        await websocket.close(code=4001, reason="Invalid or missing token")
        return

    channel = await channel_manager.connect_chamber(websocket, chamber_id)
    try:
        while True:
            # Keep connection alive; client can send pings
            data = await websocket.receive_text()
            # Handle client messages (e.g., ping)
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        channel_manager.disconnect(websocket, channel)
    except Exception:
        logger.exception("WS chamber error for chamber %d", chamber_id)
        channel_manager.disconnect(websocket, channel)


@router.websocket("/director/{tournament_id}/")
async def ws_director(
    websocket: WebSocket,
    tournament_id: int,
):
    """WebSocket for tournament director bird's-eye view.

    Receives events from ALL chambers in the tournament.
    """
    token = websocket.query_params.get("token")
    if not token or not await _validate_token(token):
        await websocket.close(code=4001, reason="Invalid or missing token")
        return

    channel = await channel_manager.connect_director(websocket, tournament_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        channel_manager.disconnect(websocket, channel)
    except Exception:
        logger.exception("WS director error for tournament %d", tournament_id)
        channel_manager.disconnect(websocket, channel)


@router.websocket("/student/{chamber_id}/")
async def ws_student(
    websocket: WebSocket,
    chamber_id: int,
):
    """WebSocket for student view.

    Receives chamber events relevant to students:
    legislation changes, queue updates, timer info.
    """
    token = websocket.query_params.get("token")
    if not token or not await _validate_token(token):
        await websocket.close(code=4001, reason="Invalid or missing token")
        return

    channel = await channel_manager.connect_student(websocket, chamber_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        channel_manager.disconnect(websocket, channel)
    except Exception:
        logger.exception("WS student error for chamber %d", chamber_id)
        channel_manager.disconnect(websocket, channel)


@router.websocket("/scorer/{chamber_id}/")
async def ws_scorer(
    websocket: WebSocket,
    chamber_id: int,
):
    """WebSocket for scorer/judge view.

    Receives speech and queue events for scoring workflow.
    """
    token = websocket.query_params.get("token")
    if not token or not await _validate_token(token):
        await websocket.close(code=4001, reason="Invalid or missing token")
        return

    channel = await channel_manager.connect_scorer(websocket, chamber_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        channel_manager.disconnect(websocket, channel)
    except Exception:
        logger.exception("WS scorer error for chamber %d", chamber_id)
        channel_manager.disconnect(websocket, channel)


async def _validate_token(token: str) -> bool:
    """Validate a JWT token for WebSocket connections.

    WebSocket connections can't use standard HTTP headers, so the
    token is passed as a query parameter.
    """
    try:
        verify_ws_token(token)
        return True
    except Exception:
        return False
