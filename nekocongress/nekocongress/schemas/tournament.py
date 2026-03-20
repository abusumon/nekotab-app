"""Pydantic schemas for congress tournament configuration."""

from datetime import datetime

from pydantic import BaseModel, Field


class CongressTournamentCreate(BaseModel):
    tournament_id: int
    name: str = Field(max_length=200)
    scoring_range_min: int = Field(default=1, ge=0, le=9)
    scoring_range_max: int = Field(default=8, ge=1, le=10)
    po_scoring_range_min: int = Field(default=1, ge=0, le=9)
    po_scoring_range_max: int = Field(default=8, ge=1, le=10)
    top_n_ranking: int = Field(default=8, ge=1, le=20)
    overtime_grace_seconds: int = Field(default=10, ge=0)
    overtime_penalty_per_interval: int = Field(default=1, ge=0)
    overtime_interval_seconds: int = Field(default=10, ge=1)
    wrong_side_penalty: int = Field(default=3, ge=0)
    speech_time_seconds: int = Field(default=180, ge=30)
    authorship_speech_time_seconds: int = Field(default=180, ge=30)
    questioning_time_seconds: int = Field(default=60, ge=10)
    authorship_questioning_time_seconds: int = Field(default=120, ge=10)
    questioner_segment_seconds: int = Field(default=30, ge=10)
    direct_questioning_enabled: bool = True
    geography_tiebreak_enabled: bool = False
    advancement_method: str = Field(default="COMBINED", pattern=r"^(POINTS|RANKINGS|COMBINED)$")
    normalization_method: str = Field(default="ZSCORE", pattern=r"^(ZSCORE|PERCENTILE)$")
    num_preliminary_sessions: int = Field(default=3, ge=1)
    num_elimination_sessions: int = Field(default=2, ge=0)
    chamber_size_target: int = Field(default=18, ge=10, le=25)


class CongressTournamentUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    scoring_range_min: int | None = Field(default=None, ge=0, le=9)
    scoring_range_max: int | None = Field(default=None, ge=1, le=10)
    po_scoring_range_min: int | None = Field(default=None, ge=0, le=9)
    po_scoring_range_max: int | None = Field(default=None, ge=1, le=10)
    top_n_ranking: int | None = Field(default=None, ge=1, le=20)
    overtime_grace_seconds: int | None = Field(default=None, ge=0)
    overtime_penalty_per_interval: int | None = Field(default=None, ge=0)
    overtime_interval_seconds: int | None = Field(default=None, ge=1)
    wrong_side_penalty: int | None = Field(default=None, ge=0)
    speech_time_seconds: int | None = Field(default=None, ge=30)
    authorship_speech_time_seconds: int | None = Field(default=None, ge=30)
    questioning_time_seconds: int | None = Field(default=None, ge=10)
    authorship_questioning_time_seconds: int | None = Field(default=None, ge=10)
    questioner_segment_seconds: int | None = Field(default=None, ge=10)
    direct_questioning_enabled: bool | None = None
    geography_tiebreak_enabled: bool | None = None
    advancement_method: str | None = Field(default=None, pattern=r"^(POINTS|RANKINGS|COMBINED)$")
    normalization_method: str | None = Field(default=None, pattern=r"^(ZSCORE|PERCENTILE)$")
    num_preliminary_sessions: int | None = Field(default=None, ge=1)
    num_elimination_sessions: int | None = Field(default=None, ge=0)
    chamber_size_target: int | None = Field(default=None, ge=10, le=25)


class CongressTournamentResponse(BaseModel):
    id: int
    tournament_id: int
    name: str
    scoring_range_min: int
    scoring_range_max: int
    po_scoring_range_min: int
    po_scoring_range_max: int
    top_n_ranking: int
    overtime_grace_seconds: int
    overtime_penalty_per_interval: int
    overtime_interval_seconds: int
    wrong_side_penalty: int
    speech_time_seconds: int
    authorship_speech_time_seconds: int
    questioning_time_seconds: int
    authorship_questioning_time_seconds: int
    questioner_segment_seconds: int
    direct_questioning_enabled: bool
    geography_tiebreak_enabled: bool
    advancement_method: str
    normalization_method: str
    num_preliminary_sessions: int
    num_elimination_sessions: int
    chamber_size_target: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
