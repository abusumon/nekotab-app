"""Pydantic schemas for scoring and rankings."""

from datetime import datetime

from pydantic import BaseModel, Field


class SpeechScoreCreate(BaseModel):
    speech_id: int
    scorer_id: int
    points: int = Field(ge=0, le=10)
    feedback: str | None = None


class SpeechScoreUpdate(BaseModel):
    points: int | None = Field(default=None, ge=0, le=10)
    feedback: str | None = None


class SpeechScoreResponse(BaseModel):
    id: int
    speech_id: int
    scorer_id: int
    points: int
    feedback: str | None
    submitted_at: datetime
    created_at: datetime


class RankingCreate(BaseModel):
    session_id: int
    scorer_id: int
    rankings: list["RankingEntry"]


class RankingEntry(BaseModel):
    legislator_id: int
    rank_position: int = Field(ge=1)


class ParliamentarianRankingCreate(BaseModel):
    session_id: int
    scorer_id: int
    rankings: list[RankingEntry]


class RankingResponse(BaseModel):
    id: int
    session_id: int
    scorer_id: int
    legislator_id: int
    legislator_name: str = ""
    rank_position: int
    is_parliamentarian_ranking: bool
    created_at: datetime


class POScoreCreate(BaseModel):
    session_id: int
    scorer_id: int
    hour_number: int = Field(ge=1)
    points: int = Field(ge=0, le=10)
    feedback: str | None = None


class POScoreResponse(BaseModel):
    id: int
    session_id: int
    scorer_id: int
    hour_number: int
    points: int
    feedback: str | None
    created_at: datetime


class SessionScoresResponse(BaseModel):
    session_id: int
    speech_scores: list[SpeechScoreResponse]
    rankings: list[RankingResponse]
    po_scores: list[POScoreResponse]
