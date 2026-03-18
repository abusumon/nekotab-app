"""Pydantic schemas for IE entries."""

from datetime import datetime

from pydantic import BaseModel, Field

from nekospeech.models.speech_event import ScratchStatus


class IEEntryCreate(BaseModel):
    event_id: int
    speaker_id: int
    partner_id: int | None = None


class IEEntryBulkCreate(BaseModel):
    event_id: int
    entries: list[IEEntryCreate] = Field(..., max_length=500)


class IEEntryResponse(BaseModel):
    id: int
    event_id: int
    speaker_id: int
    partner_id: int | None
    institution_id: int | None
    scratch_status: ScratchStatus
    created_at: datetime
    speaker_name: str = ""
    institution_name: str = ""
    institution_code: str = ""

    model_config = {"from_attributes": True}
