"""Pydantic schemas for ballot submission and results."""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class BallotLine(BaseModel):
    entry_id: int
    rank: int = Field(..., gt=0)
    speaker_points: float = Field(..., ge=0.0, le=30.0)


class BallotSubmit(BaseModel):
    room_id: int
    results: list[BallotLine] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_unique_ranks(self) -> "BallotSubmit":
        ranks = [r.rank for r in self.results]
        if len(ranks) != len(set(ranks)):
            raise ValueError("Ranks must be unique within a ballot")
        entry_ids = [r.entry_id for r in self.results]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("Duplicate entry_id in ballot")
        # Ranks must be a contiguous 1..N sequence
        if sorted(ranks) != list(range(1, len(ranks) + 1)):
            raise ValueError("Ranks must be a contiguous sequence from 1 to N")
        return self


class BallotSubmitResponse(BaseModel):
    submitted: bool
    round_complete: bool


class IEResultResponse(BaseModel):
    id: int
    room_id: int
    entry_id: int
    rank: int
    speaker_points: float
    submitted_by_judge_id: int | None
    confirmed: bool
    submitted_at: datetime
    speaker_name: str = ""
    institution_code: str = ""

    model_config = {"from_attributes": True}


class IEResultUpdate(BaseModel):
    rank: int | None = Field(default=None, gt=0)
    speaker_points: float | None = Field(default=None, ge=0.0, le=30.0)
