"""SQLAlchemy async Table definitions for the speech_events schema.

All tables live in the 'speech_events' Postgres schema to avoid collisions
with Django's default (public) schema tables.
"""

import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    func,
)

SCHEMA = "speech_events"
metadata = MetaData(schema=SCHEMA)


# ---------- Python enums mirroring Postgres enums ----------

class EventType(str, enum.Enum):
    ORATORY = "ORATORY"
    DI = "DI"
    HI = "HI"
    DUO = "DUO"
    PROSE = "PROSE"
    POETRY = "POETRY"
    EXTEMP = "EXTEMP"


class TiebreakMethod(str, enum.Enum):
    TRUNC = "TRUNC"
    LOW = "LOW"


class ScratchStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    SCRATCHED = "SCRATCHED"


class BallotStatus(str, enum.Enum):
    NO_BALLOT = "no_ballot"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"


# ---------- Tables ----------

speech_event = Table(
    "speech_event",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("tournament_id", Integer, nullable=False),
    Column("name", String(200), nullable=False),
    Column("abbreviation", String(20), nullable=False),
    Column("event_type", Enum(EventType, name="event_type", schema=SCHEMA, create_type=False), nullable=False),
    Column("num_rounds", Integer, nullable=False, server_default="3"),
    Column("room_size", Integer, nullable=False, server_default="6"),
    Column(
        "tiebreak_method",
        Enum(TiebreakMethod, name="tiebreak_method", schema=SCHEMA, create_type=False),
        nullable=False,
        server_default="TRUNC",
    ),
    Column("is_active", Boolean, nullable=False, server_default="true"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index("idx_speech_event_tournament", "tournament_id"),
)

ie_entry = Table(
    "ie_entry",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("event_id", Integer, ForeignKey(f"{SCHEMA}.speech_event.id", ondelete="CASCADE"), nullable=False),
    Column("speaker_id", Integer, nullable=False),
    Column("partner_id", Integer, nullable=True),
    Column("institution_id", Integer, nullable=True),
    Column(
        "scratch_status",
        Enum(ScratchStatus, name="scratch_status", schema=SCHEMA, create_type=False),
        nullable=False,
        server_default="ACTIVE",
    ),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("event_id", "speaker_id", name="uq_ie_entry_event_speaker"),
    Index("idx_ie_entry_event", "event_id"),
    Index("idx_ie_entry_speaker", "speaker_id"),
)

ie_room = Table(
    "ie_room",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("event_id", Integer, ForeignKey(f"{SCHEMA}.speech_event.id", ondelete="CASCADE"), nullable=False),
    Column("round_number", Integer, nullable=False),
    Column("room_number", Integer, nullable=False),
    Column("judge_id", Integer, nullable=True),
    Column("nickname", String(100), nullable=True),
    Column("confirmed", Boolean, nullable=False, server_default="false"),
    Column(
        "ballot_status",
        Enum(BallotStatus, name="ballot_status", schema=SCHEMA, create_type=False),
        nullable=False,
        server_default="no_ballot",
    ),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("event_id", "round_number", "room_number", name="uq_ie_room_event_round_room"),
    Index("idx_ie_room_event_round", "event_id", "round_number"),
)

ie_room_entry = Table(
    "ie_room_entry",
    metadata,
    Column("room_id", Integer, ForeignKey(f"{SCHEMA}.ie_room.id", ondelete="CASCADE"), nullable=False, primary_key=True),
    Column("entry_id", Integer, ForeignKey(f"{SCHEMA}.ie_entry.id", ondelete="CASCADE"), nullable=False, primary_key=True),
    Index("idx_ie_room_entry_entry", "entry_id"),
)

ie_result = Table(
    "ie_result",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("room_id", Integer, ForeignKey(f"{SCHEMA}.ie_room.id", ondelete="CASCADE"), nullable=False),
    Column("entry_id", Integer, ForeignKey(f"{SCHEMA}.ie_entry.id", ondelete="CASCADE"), nullable=False),
    Column("rank", Integer, nullable=False),
    Column("speaker_points", Numeric(5, 2), nullable=False),
    Column("submitted_by_judge_id", Integer, nullable=True),
    Column("confirmed", Boolean, nullable=False, server_default="false"),
    Column("submitted_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("room_id", "entry_id", name="uq_ie_result_room_entry"),
    UniqueConstraint("room_id", "rank", name="uq_ie_result_room_rank"),
    Index("idx_ie_result_room", "room_id"),
    Index("idx_ie_result_entry", "entry_id"),
)
