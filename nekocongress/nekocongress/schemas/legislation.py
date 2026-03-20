"""Pydantic schemas for legislation and docket."""

from datetime import datetime

from pydantic import BaseModel, Field


class LegislationCreate(BaseModel):
    congress_tournament_id: int
    title: str = Field(max_length=500)
    legislation_type: str = Field(pattern=r"^(BILL|RESOLUTION)$")
    category: str | None = Field(default=None, max_length=50)
    author_institution_id: int | None = None
    full_text: str | None = None
    docket_code: str = Field(max_length=20)


class LegislationUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    legislation_type: str | None = Field(default=None, pattern=r"^(BILL|RESOLUTION)$")
    category: str | None = Field(default=None, max_length=50)
    author_institution_id: int | None = None
    full_text: str | None = None
    docket_code: str | None = Field(default=None, max_length=20)


class LegislationResponse(BaseModel):
    id: int
    congress_tournament_id: int
    title: str
    legislation_type: str
    category: str | None
    author_institution_id: int | None
    full_text: str | None
    docket_code: str
    created_at: datetime
    updated_at: datetime


class DocketAssignRequest(BaseModel):
    session_id: int
    legislation_id: int
    agenda_order: int = Field(ge=1)


class DocketReorderRequest(BaseModel):
    """List of legislation_id in the new order."""
    item_ids: list[int]


class DocketItemResponse(BaseModel):
    id: int
    session_id: int
    legislation_id: int
    agenda_order: int
    status: str
    vote_result: str | None
    aff_votes: int | None
    neg_votes: int | None
    abstain_votes: int | None
    legislation_title: str = ""
    legislation_type: str = ""
    docket_code: str = ""
    created_at: datetime
    updated_at: datetime


class DocketResponse(BaseModel):
    session_id: int
    items: list[DocketItemResponse]
