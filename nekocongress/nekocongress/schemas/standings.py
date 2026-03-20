"""Pydantic schemas for standings and advancement."""

from datetime import datetime

from pydantic import BaseModel


class LegislatorStanding(BaseModel):
    legislator_id: int
    display_name: str
    institution_code: str = ""
    chamber_label: str = ""
    total_points: float
    total_penalties: int
    net_points: float
    speech_count: int
    avg_points_per_speech: float
    ranking_sum: float  # Lower is better
    ranking_count: int
    parliamentarian_rank: int | None = None
    po_points: float = 0.0
    normalized_score: float | None = None  # Z-score or percentile
    advancement_rank: int | None = None


class SessionBreakdown(BaseModel):
    session_id: int
    session_number: int
    chamber_label: str
    speeches: list["SpeechBreakdown"]
    ranking_positions: list["RankingBreakdown"]
    po_hours: list["POBreakdown"] = []


class SpeechBreakdown(BaseModel):
    speech_id: int
    legislation_title: str
    side: str
    speech_type: str
    scores: list["ScoreDetail"]
    penalties: int
    wrong_side: bool
    overtime: bool


class ScoreDetail(BaseModel):
    scorer_id: int
    points: int
    feedback: str | None = None


class RankingBreakdown(BaseModel):
    scorer_id: int
    rank_position: int
    is_parliamentarian: bool


class POBreakdown(BaseModel):
    hour_number: int
    scorer_id: int
    points: int


class StandingsResponse(BaseModel):
    tournament_id: int
    standings: list[LegislatorStanding]
    last_updated: datetime | None = None


class ChamberStandingsResponse(BaseModel):
    chamber_id: int
    chamber_label: str
    standings: list[LegislatorStanding]


class AdvancementResponse(BaseModel):
    tournament_id: int
    advancement_method: str
    normalization_method: str
    advancing: list[LegislatorStanding]
    cutoff_rank: int
