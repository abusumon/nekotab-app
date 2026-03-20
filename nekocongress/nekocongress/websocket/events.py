"""WebSocket event type definitions for nekocongress.

All events are typed for type safety and documentation.
Events are published to Redis channels and forwarded to WebSocket clients.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class EventType(str, Enum):
    # Floor events
    SPEAKER_RECOGNIZED = "SPEAKER_RECOGNIZED"
    SPEECH_STARTED = "SPEECH_STARTED"
    SPEECH_ENDED = "SPEECH_ENDED"
    QUEUE_UPDATED = "QUEUE_UPDATED"
    QUESTIONS_OPENED = "QUESTIONS_OPENED"
    QUESTIONER_RECOGNIZED = "QUESTIONER_RECOGNIZED"
    QUESTIONS_CLOSED = "QUESTIONS_CLOSED"
    LEGISLATION_CHANGED = "LEGISLATION_CHANGED"
    VOTE_CALLED = "VOTE_CALLED"
    VOTE_RECORDED = "VOTE_RECORDED"

    # Score events
    SCORE_SUBMITTED = "SCORE_SUBMITTED"
    RANKING_SUBMITTED = "RANKING_SUBMITTED"

    # Session events
    SESSION_STARTED = "SESSION_STARTED"
    SESSION_CLOSED = "SESSION_CLOSED"
    PO_ELECTED = "PO_ELECTED"
    PO_ELECTION_UPDATE = "PO_ELECTION_UPDATE"

    # Timer events
    TIMER_TICK = "TIMER_TICK"
    TIMER_WARNING = "TIMER_WARNING"
    TIMER_EXPIRED = "TIMER_EXPIRED"

    # Amendment events
    AMENDMENT_SUBMITTED = "AMENDMENT_SUBMITTED"
    AMENDMENT_REVIEWED = "AMENDMENT_REVIEWED"


class WebSocketEvent(BaseModel):
    """Base event structure for all WebSocket messages."""

    event_type: EventType
    chamber_id: int
    session_id: int | None = None
    timestamp: datetime
    data: dict
