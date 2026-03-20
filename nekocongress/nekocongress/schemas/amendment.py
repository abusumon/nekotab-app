"""Pydantic schemas for amendments."""

from datetime import datetime

from pydantic import BaseModel, Field


class AmendmentCreate(BaseModel):
    docket_item_id: int
    submitted_by_legislator_id: int
    amendment_text: str = Field(min_length=1)


class AmendmentReviewRequest(BaseModel):
    is_germane: bool


class AmendmentResponse(BaseModel):
    id: int
    docket_item_id: int
    submitted_by_legislator_id: int
    submitted_by_name: str = ""
    amendment_text: str
    status: str
    reviewed_at: datetime | None
    is_germane: bool | None
    created_at: datetime
    updated_at: datetime
