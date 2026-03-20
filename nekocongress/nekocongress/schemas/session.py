"""Pydantic schemas for sessions."""

from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    chamber_id: int
    session_number: int = Field(ge=1)
    session_duration_minutes: int = Field(default=150, ge=30)


class SessionResponse(BaseModel):
    id: int
    chamber_id: int
    session_number: int
    status: str
    po_legislator_id: int | None
    po_name: str = ""
    session_duration_minutes: int
    started_at: datetime | None
    closed_at: datetime | None
    current_docket_item_id: int | None
    current_speech_number: int
    next_side: str
    created_at: datetime
    updated_at: datetime


class POElectionBallot(BaseModel):
    session_id: int
    voter_legislator_id: int
    candidate_legislator_id: int


class POElectionTally(BaseModel):
    session_id: int
    round_number: int
    status: str
    candidates: list["CandidateTally"]
    total_votes: int
    majority_needed: int
    winner_id: int | None = None
    winner_name: str = ""


class CandidateTally(BaseModel):
    legislator_id: int
    display_name: str
    votes: int
    eliminated: bool = False


class PrecedenceEntry(BaseModel):
    legislator_id: int
    display_name: str
    institution_code: str = ""
    speech_count: int
    last_speech_at: datetime | None
    queue_position: int
    eligible: bool = True
    ineligibility_reason: str = ""


class PrecedenceQueueResponse(BaseModel):
    session_id: int
    next_side: str
    queue: list[PrecedenceEntry]


class QuestionerQueueResponse(BaseModel):
    session_id: int
    queue: list[PrecedenceEntry]
