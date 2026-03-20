"""Pydantic schemas for IE rooms and draw."""

from datetime import datetime

from pydantic import BaseModel

from nekospeech.models.speech_event import BallotStatus
from nekospeech.schemas.entry import IEEntryResponse


class IERoomEntryResponse(BaseModel):
    entry: IEEntryResponse


class RenameRoomRequest(BaseModel):
    room_id: int
    nickname: str | None = None


class IERoomResponse(BaseModel):
    id: int
    event_id: int
    round_number: int
    room_number: int
    nickname: str | None = None
    judge_id: int | None
    judge_name: str = ""
    confirmed: bool
    ballot_status: str = "no_ballot"
    created_at: datetime
    entries: list[IEEntryResponse] = []

    model_config = {"from_attributes": True}


class DrawGenerateRequest(BaseModel):
    event_id: int
    round_number: int
    force: bool = False
    finalist_entry_ids: list[int] | None = None


class AssignJudgeRequest(BaseModel):
    room_id: int
    judge_id: int


class DrawResponse(BaseModel):
    event_id: int
    round_number: int
    rooms: list[IERoomResponse]
