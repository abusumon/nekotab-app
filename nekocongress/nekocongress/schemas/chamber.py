"""Pydantic schemas for chambers."""

from datetime import datetime

from pydantic import BaseModel, Field


class ChamberCreate(BaseModel):
    congress_tournament_id: int
    label: str = Field(max_length=100)
    chamber_type: str = Field(default="HOUSE", pattern=r"^(HOUSE|SENATE)$")
    chamber_number: int = Field(ge=1)
    is_elimination: bool = False


class ChamberResponse(BaseModel):
    id: int
    congress_tournament_id: int
    label: str
    chamber_type: str
    chamber_number: int
    is_elimination: bool
    created_at: datetime
    updated_at: datetime
    legislator_count: int = 0
    session_count: int = 0


class ChamberAssignRequest(BaseModel):
    legislator_ids: list[int]


class ChamberAssignmentResponse(BaseModel):
    id: int
    chamber_id: int
    legislator_id: int
    seat_number: int | None
    legislator_name: str = ""
    institution_code: str = ""
    created_at: datetime


class SeatingChartResponse(BaseModel):
    chamber_id: int
    chamber_label: str
    assignments: list[ChamberAssignmentResponse]
