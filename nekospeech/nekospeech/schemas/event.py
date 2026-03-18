"""Pydantic schemas for SpeechEvent CRUD."""

from datetime import datetime

from pydantic import BaseModel, Field

from nekospeech.models.speech_event import EventType, TiebreakMethod


class SpeechEventCreate(BaseModel):
    tournament_id: int
    name: str = Field(..., min_length=1, max_length=200)
    abbreviation: str = Field(..., min_length=1, max_length=20)
    event_type: EventType
    num_rounds: int = Field(default=3, gt=0)
    room_size: int = Field(default=6, ge=2, le=12)
    tiebreak_method: TiebreakMethod = TiebreakMethod.TRUNC


class SpeechEventUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    abbreviation: str | None = Field(default=None, min_length=1, max_length=20)
    num_rounds: int | None = Field(default=None, gt=0)
    room_size: int | None = Field(default=None, ge=2, le=12)
    tiebreak_method: TiebreakMethod | None = None


class SpeechEventResponse(BaseModel):
    id: int
    tournament_id: int
    name: str
    abbreviation: str
    event_type: EventType
    num_rounds: int
    room_size: int
    tiebreak_method: TiebreakMethod
    is_active: bool
    created_at: datetime
    entry_count: int = 0
    rounds_with_draw: list[int] = []

    model_config = {"from_attributes": True}
