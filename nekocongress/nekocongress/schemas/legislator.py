"""Pydantic schemas for legislators."""

from datetime import datetime

from pydantic import BaseModel, Field


class LegislatorCreate(BaseModel):
    congress_tournament_id: int
    speaker_id: int
    display_name: str = Field(max_length=200)
    institution_id: int | None = None
    institution_code: str | None = Field(default=None, max_length=20)


class LegislatorBulkCreate(BaseModel):
    congress_tournament_id: int
    legislators: list[LegislatorCreate]


class LegislatorResponse(BaseModel):
    id: int
    congress_tournament_id: int
    speaker_id: int
    display_name: str
    institution_id: int | None
    institution_code: str | None
    is_withdrawn: bool
    created_at: datetime
    updated_at: datetime
