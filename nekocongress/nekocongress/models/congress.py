"""SQLAlchemy Table definitions for the congress_events schema.

All tables are defined as Core Table objects (not ORM models) to match
the nekospeech pattern. These map to the tables created in
migrations/001_create_congress_events_schema.sql.
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

# PostgreSQL ENUMs living in the congress_events schema.
# create_type=False because the migration already created them.
_enum_kw = dict(schema="congress_events", create_type=False)

AdvancementMethod = Enum("POINTS", "RANKINGS", "COMBINED", name="advancement_method", **_enum_kw)
NormalizationMethod = Enum("ZSCORE", "PERCENTILE", name="normalization_method", **_enum_kw)
ChamberType = Enum("HOUSE", "SENATE", name="chamber_type", **_enum_kw)
SessionStatus = Enum("PENDING", "ACTIVE", "CLOSED", name="session_status", **_enum_kw)
LegislationType = Enum("BILL", "RESOLUTION", name="legislation_type", **_enum_kw)
DocketStatus = Enum("PENDING", "DEBATING", "VOTED", "TABLED", "CARRIED_OVER", name="docket_status", **_enum_kw)
VoteResult = Enum("PASS", "FAIL", "TABLED", name="vote_result", **_enum_kw)
SpeechSide = Enum("AFF", "NEG", "AUTHORSHIP", "SPONSORSHIP", name="speech_side", **_enum_kw)
SpeechType = Enum("AUTHORSHIP", "SPONSORSHIP", "STANDARD", name="speech_type", **_enum_kw)
AmendmentStatus = Enum("SUBMITTED", "ACCEPTED", "REJECTED", "DEBATED", "WITHDRAWN", name="amendment_status", **_enum_kw)
ElectionStatus = Enum("OPEN", "ELIMINATED", "DECIDED", name="election_status", **_enum_kw)

congress_metadata = MetaData(schema="congress_events")

congress_tournament = Table(
    "congress_tournament",
    congress_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("tournament_id", Integer, nullable=False),
    Column("name", String(200), nullable=False),
    Column("scoring_range_min", Integer, nullable=False, server_default="1"),
    Column("scoring_range_max", Integer, nullable=False, server_default="8"),
    Column("po_scoring_range_min", Integer, nullable=False, server_default="1"),
    Column("po_scoring_range_max", Integer, nullable=False, server_default="8"),
    Column("top_n_ranking", Integer, nullable=False, server_default="8"),
    Column("overtime_grace_seconds", Integer, nullable=False, server_default="10"),
    Column("overtime_penalty_per_interval", Integer, nullable=False, server_default="1"),
    Column("overtime_interval_seconds", Integer, nullable=False, server_default="10"),
    Column("wrong_side_penalty", Integer, nullable=False, server_default="3"),
    Column("speech_time_seconds", Integer, nullable=False, server_default="180"),
    Column("authorship_speech_time_seconds", Integer, nullable=False, server_default="180"),
    Column("questioning_time_seconds", Integer, nullable=False, server_default="60"),
    Column("authorship_questioning_time_seconds", Integer, nullable=False, server_default="120"),
    Column("questioner_segment_seconds", Integer, nullable=False, server_default="30"),
    Column("direct_questioning_enabled", Boolean, nullable=False, server_default="true"),
    Column("geography_tiebreak_enabled", Boolean, nullable=False, server_default="false"),
    Column("advancement_method", AdvancementMethod, nullable=False, server_default="COMBINED"),
    Column("normalization_method", NormalizationMethod, nullable=False, server_default="ZSCORE"),
    Column("num_preliminary_sessions", Integer, nullable=False, server_default="3"),
    Column("num_elimination_sessions", Integer, nullable=False, server_default="2"),
    Column("chamber_size_target", Integer, nullable=False, server_default="18"),
    Column("is_active", Boolean, nullable=False, server_default="true"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    autoload_with=None,
)

congress_chamber = Table(
    "congress_chamber",
    congress_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("congress_tournament_id", BigInteger, nullable=False),
    Column("label", String(100), nullable=False),
    Column("chamber_type", ChamberType, nullable=False, server_default="HOUSE"),
    Column("chamber_number", Integer, nullable=False),
    Column("is_elimination", Boolean, nullable=False, server_default="false"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    autoload_with=None,
)

congress_legislator = Table(
    "congress_legislator",
    congress_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("congress_tournament_id", BigInteger, nullable=False),
    Column("speaker_id", Integer, nullable=False),
    Column("display_name", String(200), nullable=False),
    Column("institution_id", Integer, nullable=True),
    Column("institution_code", String(20), nullable=True),
    Column("is_withdrawn", Boolean, nullable=False, server_default="false"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    autoload_with=None,
)

congress_chamber_assignment = Table(
    "congress_chamber_assignment",
    congress_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("chamber_id", BigInteger, nullable=False),
    Column("legislator_id", BigInteger, nullable=False),
    Column("seat_number", Integer, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    autoload_with=None,
)

congress_legislation = Table(
    "congress_legislation",
    congress_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("congress_tournament_id", BigInteger, nullable=False),
    Column("title", String(500), nullable=False),
    Column("legislation_type", LegislationType, nullable=False),
    Column("category", String(50), nullable=True),
    Column("author_institution_id", Integer, nullable=True),
    Column("full_text", Text, nullable=True),
    Column("docket_code", String(20), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    autoload_with=None,
)

congress_session = Table(
    "congress_session",
    congress_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("chamber_id", BigInteger, nullable=False),
    Column("session_number", Integer, nullable=False),
    Column("status", SessionStatus, nullable=False, server_default="PENDING"),
    Column("po_legislator_id", BigInteger, nullable=True),
    Column("session_duration_minutes", Integer, nullable=False, server_default="150"),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("closed_at", DateTime(timezone=True), nullable=True),
    Column("current_docket_item_id", BigInteger, nullable=True),
    Column("current_speech_number", Integer, nullable=False, server_default="0"),
    Column("next_side", String(3), nullable=False, server_default="AFF"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    autoload_with=None,
)

congress_docket_item = Table(
    "congress_docket_item",
    congress_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("session_id", BigInteger, nullable=False),
    Column("legislation_id", BigInteger, nullable=False),
    Column("agenda_order", Integer, nullable=False),
    Column("status", DocketStatus, nullable=False, server_default="PENDING"),
    Column("vote_result", VoteResult, nullable=True),
    Column("aff_votes", Integer, nullable=True),
    Column("neg_votes", Integer, nullable=True),
    Column("abstain_votes", Integer, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    autoload_with=None,
)

congress_speech = Table(
    "congress_speech",
    congress_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("session_id", BigInteger, nullable=False),
    Column("docket_item_id", BigInteger, nullable=False),
    Column("legislator_id", BigInteger, nullable=False),
    Column("speech_number", Integer, nullable=False),
    Column("session_speech_number", Integer, nullable=False),
    Column("side", SpeechSide, nullable=False),
    Column("speech_type", SpeechType, nullable=False, server_default="STANDARD"),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("ended_at", DateTime(timezone=True), nullable=True),
    Column("duration_seconds", Integer, nullable=True),
    Column("is_overtime", Boolean, nullable=False, server_default="false"),
    Column("overtime_seconds", Integer, nullable=False, server_default="0"),
    Column("overtime_penalty", Integer, nullable=False, server_default="0"),
    Column("wrong_side", Boolean, nullable=False, server_default="false"),
    Column("wrong_side_penalty", Integer, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    autoload_with=None,
)

congress_question_period = Table(
    "congress_question_period",
    congress_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("speech_id", BigInteger, nullable=False),
    Column("total_time_seconds", Integer, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("ended_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    autoload_with=None,
)

congress_questioner = Table(
    "congress_questioner",
    congress_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("question_period_id", BigInteger, nullable=False),
    Column("legislator_id", BigInteger, nullable=False),
    Column("segment_number", Integer, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("ended_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    autoload_with=None,
)

congress_score = Table(
    "congress_score",
    congress_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("speech_id", BigInteger, nullable=False),
    Column("scorer_id", Integer, nullable=False),
    Column("points", Integer, nullable=False),
    Column("feedback", Text, nullable=True),
    Column("submitted_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    autoload_with=None,
)

congress_ranking = Table(
    "congress_ranking",
    congress_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("session_id", BigInteger, nullable=False),
    Column("scorer_id", Integer, nullable=False),
    Column("legislator_id", BigInteger, nullable=False),
    Column("rank_position", Integer, nullable=False),
    Column("is_parliamentarian_ranking", Boolean, nullable=False, server_default="false"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    autoload_with=None,
)

congress_po_election = Table(
    "congress_po_election",
    congress_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("session_id", BigInteger, nullable=False),
    Column("round_number", Integer, nullable=False, server_default="1"),
    Column("status", ElectionStatus, nullable=False, server_default="OPEN"),
    Column("winner_legislator_id", BigInteger, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    autoload_with=None,
)

congress_po_ballot = Table(
    "congress_po_ballot",
    congress_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("election_id", BigInteger, nullable=False),
    Column("voter_legislator_id", BigInteger, nullable=False),
    Column("candidate_legislator_id", BigInteger, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    autoload_with=None,
)

congress_po_score = Table(
    "congress_po_score",
    congress_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("session_id", BigInteger, nullable=False),
    Column("scorer_id", Integer, nullable=False),
    Column("hour_number", Integer, nullable=False),
    Column("points", Integer, nullable=False),
    Column("feedback", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    autoload_with=None,
)

congress_amendment = Table(
    "congress_amendment",
    congress_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("docket_item_id", BigInteger, nullable=False),
    Column("submitted_by_legislator_id", BigInteger, nullable=False),
    Column("amendment_text", Text, nullable=False),
    Column("status", AmendmentStatus, nullable=False, server_default="SUBMITTED"),
    Column("reviewed_at", DateTime(timezone=True), nullable=True),
    Column("is_germane", Boolean, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    autoload_with=None,
)

congress_precedence_state = Table(
    "congress_precedence_state",
    congress_metadata,
    Column("id", BigInteger, primary_key=True),
    Column("session_id", BigInteger, nullable=False),
    Column("legislator_id", BigInteger, nullable=False),
    Column("speech_count", Integer, nullable=False, server_default="0"),
    Column("last_speech_at", DateTime(timezone=True), nullable=True),
    Column("question_count", Integer, nullable=False, server_default="0"),
    Column("last_question_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    autoload_with=None,
)
