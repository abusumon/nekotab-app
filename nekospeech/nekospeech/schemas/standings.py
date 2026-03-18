"""Pydantic schemas for standings."""

from pydantic import BaseModel


class StandingsRow(BaseModel):
    rank: int
    entry_id: int
    speaker_id: int
    speaker_name: str
    institution_name: str
    institution_code: str
    truncated_rank_sum: float
    total_speaker_points: float
    lowest_single_rank: int
    rounds_competed: int


class StandingsResponse(BaseModel):
    event_id: int
    rounds_complete: int
    entries: list[StandingsRow]
