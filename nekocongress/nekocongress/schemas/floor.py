"""Pydantic schemas for floor management (speeches, questions, votes)."""

from datetime import datetime

from pydantic import BaseModel, Field


class RecognizeSpeakerRequest(BaseModel):
    session_id: int
    legislator_id: int | None = None  # None = auto-select from queue
    side: str | None = None  # Override side (AFF/NEG) if needed
    speech_type: str = Field(default="STANDARD", pattern=r"^(AUTHORSHIP|SPONSORSHIP|STANDARD)$")
    is_wrong_side: bool = False


class StartSpeechRequest(BaseModel):
    session_id: int
    speech_id: int


class EndSpeechRequest(BaseModel):
    session_id: int
    speech_id: int


class OpenQuestionsRequest(BaseModel):
    speech_id: int


class RecognizeQuestionerRequest(BaseModel):
    session_id: int
    speech_id: int
    legislator_id: int | None = None  # None = auto-select from questioner queue


class CloseQuestionsRequest(BaseModel):
    speech_id: int


class ChangeLegislationRequest(BaseModel):
    session_id: int
    docket_item_id: int | None = None  # None = next in agenda order


class CallVoteRequest(BaseModel):
    session_id: int
    docket_item_id: int


class RecordVoteRequest(BaseModel):
    session_id: int
    docket_item_id: int
    result: str = Field(pattern=r"^(PASS|FAIL|TABLED)$")
    aff_votes: int = Field(ge=0)
    neg_votes: int = Field(ge=0)
    abstain_votes: int = Field(default=0, ge=0)


class SpeechResponse(BaseModel):
    id: int
    session_id: int
    docket_item_id: int
    legislator_id: int
    legislator_name: str = ""
    institution_code: str = ""
    speech_number: int
    session_speech_number: int
    side: str
    speech_type: str
    started_at: datetime | None
    ended_at: datetime | None
    duration_seconds: int | None
    is_overtime: bool
    overtime_seconds: int
    overtime_penalty: int
    wrong_side: bool
    wrong_side_penalty: int
    created_at: datetime


class QuestionPeriodResponse(BaseModel):
    id: int
    speech_id: int
    total_time_seconds: int
    started_at: datetime | None
    ended_at: datetime | None
    questioners: list["QuestionerResponse"] = []


class QuestionerResponse(BaseModel):
    id: int
    legislator_id: int
    legislator_name: str = ""
    segment_number: int
    started_at: datetime | None
    ended_at: datetime | None
