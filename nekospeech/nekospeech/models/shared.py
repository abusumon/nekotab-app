"""Read-only SQLAlchemy Table mappings for Django's participant tables.

These tables live in the default 'public' schema and are NEVER written to
by nekospeech. They exist solely for JOINs when we need speaker names,
institution codes, or tournament metadata.

Django uses multi-table inheritance: Speaker and Adjudicator both extend
Person.  The `name` field lives on `participants_person`; child tables
reference it via `person_ptr_id`.
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
)

# Public schema — these are Django's tables
shared_metadata = MetaData(schema="public")

participants_person = Table(
    "participants_person",
    shared_metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(70), nullable=False),
    Column("email", String(254), nullable=True),
    Column("gender", String(1), nullable=True),
    autoload_with=None,  # we define columns explicitly; no runtime reflection
)

participants_speaker = Table(
    "participants_speaker",
    shared_metadata,
    Column("person_ptr_id", Integer, primary_key=True),  # FK to participants_person.id
    Column("team_id", Integer, nullable=False),
    autoload_with=None,
)

participants_team = Table(
    "participants_team",
    shared_metadata,
    Column("id", Integer, primary_key=True),
    Column("institution_id", Integer, nullable=True),
    Column("tournament_id", Integer, nullable=False),
    autoload_with=None,
)

participants_institution = Table(
    "participants_institution",
    shared_metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("code", String(20), nullable=False),
    autoload_with=None,
)

participants_adjudicator = Table(
    "participants_adjudicator",
    shared_metadata,
    Column("person_ptr_id", Integer, primary_key=True),  # FK to participants_person.id
    Column("institution_id", Integer, nullable=True),
    Column("tournament_id", Integer, nullable=True),
    Column("base_score", Float, nullable=True),
    Column("trainee", Boolean, nullable=False),
    autoload_with=None,
)

tournaments_tournament = Table(
    "tournaments_tournament",
    shared_metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False),
    Column("short_name", String(25), nullable=True),
    Column("slug", String(50), nullable=False),
    Column("active", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=True),
    autoload_with=None,
)
