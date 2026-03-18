-- Migration 001: Create the speech_events schema and all IE tables.
-- This schema is owned by the nekospeech service. Django never writes here.

CREATE SCHEMA IF NOT EXISTS speech_events;

-- Enum for event types
DO $$ BEGIN
    CREATE TYPE speech_events.event_type AS ENUM (
        'ORATORY', 'DI', 'HI', 'DUO', 'PROSE', 'POETRY', 'EXTEMP'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Enum for tiebreak methods
DO $$ BEGIN
    CREATE TYPE speech_events.tiebreak_method AS ENUM ('TRUNC', 'LOW');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Enum for scratch status
DO $$ BEGIN
    CREATE TYPE speech_events.scratch_status AS ENUM ('ACTIVE', 'SCRATCHED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================
-- SpeechEvent — one per IE event type per tournament
-- ============================================================
CREATE TABLE IF NOT EXISTS speech_events.speech_event (
    id              SERIAL PRIMARY KEY,
    tournament_id   INTEGER NOT NULL,       -- FK to public.tournaments_tournament(id)
    name            VARCHAR(200) NOT NULL,
    abbreviation    VARCHAR(20) NOT NULL,
    event_type      speech_events.event_type NOT NULL,
    num_rounds      INTEGER NOT NULL DEFAULT 3 CHECK (num_rounds > 0),
    room_size       INTEGER NOT NULL DEFAULT 6 CHECK (room_size BETWEEN 2 AND 12),
    tiebreak_method speech_events.tiebreak_method NOT NULL DEFAULT 'TRUNC',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_speech_event_tournament ON speech_events.speech_event (tournament_id);

-- ============================================================
-- IEEntry — one per competitor in one SpeechEvent
-- ============================================================
CREATE TABLE IF NOT EXISTS speech_events.ie_entry (
    id              SERIAL PRIMARY KEY,
    event_id        INTEGER NOT NULL REFERENCES speech_events.speech_event(id) ON DELETE CASCADE,
    speaker_id      INTEGER NOT NULL,       -- FK to public.participants_speaker(id)
    partner_id      INTEGER,                -- nullable, for DUO events
    institution_id  INTEGER,                -- denormalized from speaker for fast queries
    scratch_status  speech_events.scratch_status NOT NULL DEFAULT 'ACTIVE',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (event_id, speaker_id)
);

CREATE INDEX IF NOT EXISTS idx_ie_entry_event ON speech_events.ie_entry (event_id);
CREATE INDEX IF NOT EXISTS idx_ie_entry_speaker ON speech_events.ie_entry (speaker_id);

-- ============================================================
-- IERoom — one room per round, holds entries, one judge
-- ============================================================
CREATE TABLE IF NOT EXISTS speech_events.ie_room (
    id              SERIAL PRIMARY KEY,
    event_id        INTEGER NOT NULL REFERENCES speech_events.speech_event(id) ON DELETE CASCADE,
    round_number    INTEGER NOT NULL CHECK (round_number > 0),
    room_number     INTEGER NOT NULL CHECK (room_number > 0),
    judge_id        INTEGER,                -- FK to public.adjallocation_debateadjudicator is loose
    confirmed       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (event_id, round_number, room_number)
);

CREATE INDEX IF NOT EXISTS idx_ie_room_event_round ON speech_events.ie_room (event_id, round_number);

-- ============================================================
-- IERoomEntry — M2M join: IERoom <-> IEEntry
-- ============================================================
CREATE TABLE IF NOT EXISTS speech_events.ie_room_entry (
    room_id     INTEGER NOT NULL REFERENCES speech_events.ie_room(id) ON DELETE CASCADE,
    entry_id    INTEGER NOT NULL REFERENCES speech_events.ie_entry(id) ON DELETE CASCADE,
    PRIMARY KEY (room_id, entry_id)
);

CREATE INDEX IF NOT EXISTS idx_ie_room_entry_entry ON speech_events.ie_room_entry (entry_id);

-- ============================================================
-- IEResult — one row per entry per room (judge's ballot line)
-- ============================================================
CREATE TABLE IF NOT EXISTS speech_events.ie_result (
    id                  SERIAL PRIMARY KEY,
    room_id             INTEGER NOT NULL REFERENCES speech_events.ie_room(id) ON DELETE CASCADE,
    entry_id            INTEGER NOT NULL REFERENCES speech_events.ie_entry(id) ON DELETE CASCADE,
    rank                INTEGER NOT NULL CHECK (rank > 0),
    speaker_points      NUMERIC(5, 2) NOT NULL CHECK (speaker_points >= 0 AND speaker_points <= 30),
    submitted_by_judge_id INTEGER,
    confirmed           BOOLEAN NOT NULL DEFAULT FALSE,
    submitted_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (room_id, entry_id),
    UNIQUE (room_id, rank)          -- ranks must be unique within a room
);

CREATE INDEX IF NOT EXISTS idx_ie_result_room ON speech_events.ie_result (room_id);
CREATE INDEX IF NOT EXISTS idx_ie_result_entry ON speech_events.ie_result (entry_id);
