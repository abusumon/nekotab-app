-- Migration 001: Create the congress_events schema and all Congressional Debate tables.
-- This schema is owned by the nekocongress service. Django never writes here.

CREATE SCHEMA IF NOT EXISTS congress_events;

-- ============================================================
-- Enums
-- ============================================================

DO $$ BEGIN
    CREATE TYPE congress_events.chamber_type AS ENUM ('HOUSE', 'SENATE');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE congress_events.session_status AS ENUM ('PENDING', 'ACTIVE', 'CLOSED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE congress_events.legislation_type AS ENUM ('BILL', 'RESOLUTION');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE congress_events.docket_status AS ENUM (
        'PENDING', 'DEBATING', 'VOTED', 'TABLED', 'CARRIED_OVER'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE congress_events.vote_result AS ENUM ('PASS', 'FAIL', 'TABLED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE congress_events.speech_side AS ENUM ('AFF', 'NEG', 'AUTHORSHIP', 'SPONSORSHIP');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE congress_events.speech_type AS ENUM ('AUTHORSHIP', 'SPONSORSHIP', 'STANDARD');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE congress_events.amendment_status AS ENUM (
        'SUBMITTED', 'ACCEPTED', 'REJECTED', 'DEBATED', 'WITHDRAWN'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE congress_events.election_status AS ENUM ('OPEN', 'ELIMINATED', 'DECIDED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE congress_events.advancement_method AS ENUM ('POINTS', 'RANKINGS', 'COMBINED');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE congress_events.normalization_method AS ENUM ('ZSCORE', 'PERCENTILE');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================
-- congress_tournament — tournament-level configuration
-- ============================================================
CREATE TABLE IF NOT EXISTS congress_events.congress_tournament (
    id                              BIGSERIAL PRIMARY KEY,
    tournament_id                   INTEGER NOT NULL,
    name                            VARCHAR(200) NOT NULL,
    scoring_range_min               INTEGER NOT NULL DEFAULT 1 CHECK (scoring_range_min >= 0),
    scoring_range_max               INTEGER NOT NULL DEFAULT 8 CHECK (scoring_range_max <= 10),
    po_scoring_range_min            INTEGER NOT NULL DEFAULT 1,
    po_scoring_range_max            INTEGER NOT NULL DEFAULT 8,
    top_n_ranking                   INTEGER NOT NULL DEFAULT 8 CHECK (top_n_ranking > 0),
    overtime_grace_seconds          INTEGER NOT NULL DEFAULT 10 CHECK (overtime_grace_seconds >= 0),
    overtime_penalty_per_interval   INTEGER NOT NULL DEFAULT 1,
    overtime_interval_seconds       INTEGER NOT NULL DEFAULT 10 CHECK (overtime_interval_seconds > 0),
    wrong_side_penalty              INTEGER NOT NULL DEFAULT 3 CHECK (wrong_side_penalty >= 0),
    speech_time_seconds             INTEGER NOT NULL DEFAULT 180 CHECK (speech_time_seconds > 0),
    authorship_speech_time_seconds  INTEGER NOT NULL DEFAULT 180 CHECK (authorship_speech_time_seconds > 0),
    questioning_time_seconds        INTEGER NOT NULL DEFAULT 60 CHECK (questioning_time_seconds > 0),
    authorship_questioning_time_seconds INTEGER NOT NULL DEFAULT 120 CHECK (authorship_questioning_time_seconds > 0),
    questioner_segment_seconds      INTEGER NOT NULL DEFAULT 30 CHECK (questioner_segment_seconds > 0),
    direct_questioning_enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    geography_tiebreak_enabled      BOOLEAN NOT NULL DEFAULT FALSE,
    advancement_method              congress_events.advancement_method NOT NULL DEFAULT 'COMBINED',
    normalization_method            congress_events.normalization_method NOT NULL DEFAULT 'ZSCORE',
    num_preliminary_sessions        INTEGER NOT NULL DEFAULT 3 CHECK (num_preliminary_sessions > 0),
    num_elimination_sessions        INTEGER NOT NULL DEFAULT 2 CHECK (num_elimination_sessions >= 0),
    chamber_size_target             INTEGER NOT NULL DEFAULT 18 CHECK (chamber_size_target BETWEEN 10 AND 25),
    is_active                       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_scoring_range CHECK (scoring_range_min < scoring_range_max),
    CONSTRAINT chk_po_scoring_range CHECK (po_scoring_range_min < po_scoring_range_max)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_congress_tournament_tid
    ON congress_events.congress_tournament (tournament_id);

-- ============================================================
-- congress_chamber — a chamber within a tournament
-- ============================================================
CREATE TABLE IF NOT EXISTS congress_events.congress_chamber (
    id                      BIGSERIAL PRIMARY KEY,
    congress_tournament_id  BIGINT NOT NULL REFERENCES congress_events.congress_tournament(id) ON DELETE CASCADE,
    label                   VARCHAR(100) NOT NULL,
    chamber_type            congress_events.chamber_type NOT NULL DEFAULT 'HOUSE',
    chamber_number          INTEGER NOT NULL CHECK (chamber_number > 0),
    is_elimination          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (congress_tournament_id, chamber_number)
);

CREATE INDEX IF NOT EXISTS idx_congress_chamber_tournament
    ON congress_events.congress_chamber (congress_tournament_id);

-- ============================================================
-- congress_legislator — student participant
-- ============================================================
CREATE TABLE IF NOT EXISTS congress_events.congress_legislator (
    id                      BIGSERIAL PRIMARY KEY,
    congress_tournament_id  BIGINT NOT NULL REFERENCES congress_events.congress_tournament(id) ON DELETE CASCADE,
    speaker_id              INTEGER NOT NULL,
    display_name            VARCHAR(200) NOT NULL,
    institution_id          INTEGER,
    institution_code        VARCHAR(20),
    is_withdrawn            BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (congress_tournament_id, speaker_id)
);

CREATE INDEX IF NOT EXISTS idx_congress_legislator_tournament
    ON congress_events.congress_legislator (congress_tournament_id);

-- ============================================================
-- congress_chamber_assignment — which legislator is in which chamber
-- ============================================================
CREATE TABLE IF NOT EXISTS congress_events.congress_chamber_assignment (
    id              BIGSERIAL PRIMARY KEY,
    chamber_id      BIGINT NOT NULL REFERENCES congress_events.congress_chamber(id) ON DELETE CASCADE,
    legislator_id   BIGINT NOT NULL REFERENCES congress_events.congress_legislator(id) ON DELETE CASCADE,
    seat_number     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (chamber_id, legislator_id)
);

CREATE INDEX IF NOT EXISTS idx_congress_assignment_legislator
    ON congress_events.congress_chamber_assignment (legislator_id);

-- ============================================================
-- congress_legislation — a bill or resolution
-- ============================================================
CREATE TABLE IF NOT EXISTS congress_events.congress_legislation (
    id                      BIGSERIAL PRIMARY KEY,
    congress_tournament_id  BIGINT NOT NULL REFERENCES congress_events.congress_tournament(id) ON DELETE CASCADE,
    title                   VARCHAR(500) NOT NULL,
    legislation_type        congress_events.legislation_type NOT NULL,
    category                VARCHAR(50),
    author_institution_id   INTEGER,
    full_text               TEXT,
    docket_code             VARCHAR(20) NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (congress_tournament_id, docket_code)
);

CREATE INDEX IF NOT EXISTS idx_congress_legislation_tournament
    ON congress_events.congress_legislation (congress_tournament_id);

-- ============================================================
-- congress_session — one session within a chamber
-- ============================================================
CREATE TABLE IF NOT EXISTS congress_events.congress_session (
    id                          BIGSERIAL PRIMARY KEY,
    chamber_id                  BIGINT NOT NULL REFERENCES congress_events.congress_chamber(id) ON DELETE CASCADE,
    session_number              INTEGER NOT NULL CHECK (session_number > 0),
    status                      congress_events.session_status NOT NULL DEFAULT 'PENDING',
    po_legislator_id            BIGINT REFERENCES congress_events.congress_legislator(id),
    session_duration_minutes    INTEGER NOT NULL DEFAULT 150 CHECK (session_duration_minutes > 0),
    started_at                  TIMESTAMPTZ,
    closed_at                   TIMESTAMPTZ,
    current_docket_item_id      BIGINT,
    current_speech_number       INTEGER NOT NULL DEFAULT 0,
    next_side                   VARCHAR(3) NOT NULL DEFAULT 'AFF' CHECK (next_side IN ('AFF', 'NEG')),
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (chamber_id, session_number)
);

CREATE INDEX IF NOT EXISTS idx_congress_session_chamber
    ON congress_events.congress_session (chamber_id);
CREATE INDEX IF NOT EXISTS idx_congress_session_status
    ON congress_events.congress_session (status);

-- ============================================================
-- congress_docket_item — legislation assigned to a session
-- ============================================================
CREATE TABLE IF NOT EXISTS congress_events.congress_docket_item (
    id              BIGSERIAL PRIMARY KEY,
    session_id      BIGINT NOT NULL REFERENCES congress_events.congress_session(id) ON DELETE CASCADE,
    legislation_id  BIGINT NOT NULL REFERENCES congress_events.congress_legislation(id) ON DELETE CASCADE,
    agenda_order    INTEGER NOT NULL CHECK (agenda_order > 0),
    status          congress_events.docket_status NOT NULL DEFAULT 'PENDING',
    vote_result     congress_events.vote_result,
    aff_votes       INTEGER,
    neg_votes       INTEGER,
    abstain_votes   INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, agenda_order)
);

CREATE INDEX IF NOT EXISTS idx_congress_docket_session
    ON congress_events.congress_docket_item (session_id);
CREATE INDEX IF NOT EXISTS idx_congress_docket_legislation
    ON congress_events.congress_docket_item (legislation_id);

-- Add FK for session's current docket item now that both tables exist
ALTER TABLE congress_events.congress_session
    ADD CONSTRAINT fk_session_current_docket
    FOREIGN KEY (current_docket_item_id)
    REFERENCES congress_events.congress_docket_item(id)
    ON DELETE SET NULL;

-- ============================================================
-- congress_speech — a speech given by a legislator
-- ============================================================
CREATE TABLE IF NOT EXISTS congress_events.congress_speech (
    id                      BIGSERIAL PRIMARY KEY,
    session_id              BIGINT NOT NULL REFERENCES congress_events.congress_session(id) ON DELETE CASCADE,
    docket_item_id          BIGINT NOT NULL REFERENCES congress_events.congress_docket_item(id) ON DELETE CASCADE,
    legislator_id           BIGINT NOT NULL REFERENCES congress_events.congress_legislator(id) ON DELETE CASCADE,
    speech_number           INTEGER NOT NULL CHECK (speech_number > 0),
    session_speech_number   INTEGER NOT NULL CHECK (session_speech_number > 0),
    side                    congress_events.speech_side NOT NULL,
    speech_type             congress_events.speech_type NOT NULL DEFAULT 'STANDARD',
    started_at              TIMESTAMPTZ,
    ended_at                TIMESTAMPTZ,
    duration_seconds        INTEGER,
    is_overtime             BOOLEAN NOT NULL DEFAULT FALSE,
    overtime_seconds        INTEGER NOT NULL DEFAULT 0,
    overtime_penalty        INTEGER NOT NULL DEFAULT 0,
    wrong_side              BOOLEAN NOT NULL DEFAULT FALSE,
    wrong_side_penalty      INTEGER NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_congress_speech_session_legislator
    ON congress_events.congress_speech (session_id, legislator_id);
CREATE INDEX IF NOT EXISTS idx_congress_speech_session_number
    ON congress_events.congress_speech (session_id, session_speech_number);
CREATE INDEX IF NOT EXISTS idx_congress_speech_docket
    ON congress_events.congress_speech (docket_item_id);

-- ============================================================
-- congress_question_period — questioning period following a speech
-- ============================================================
CREATE TABLE IF NOT EXISTS congress_events.congress_question_period (
    id                  BIGSERIAL PRIMARY KEY,
    speech_id           BIGINT NOT NULL REFERENCES congress_events.congress_speech(id) ON DELETE CASCADE,
    total_time_seconds  INTEGER NOT NULL,
    started_at          TIMESTAMPTZ,
    ended_at            TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (speech_id)
);

-- ============================================================
-- congress_questioner — one questioner within a question period
-- ============================================================
CREATE TABLE IF NOT EXISTS congress_events.congress_questioner (
    id                  BIGSERIAL PRIMARY KEY,
    question_period_id  BIGINT NOT NULL REFERENCES congress_events.congress_question_period(id) ON DELETE CASCADE,
    legislator_id       BIGINT NOT NULL REFERENCES congress_events.congress_legislator(id) ON DELETE CASCADE,
    segment_number      INTEGER NOT NULL CHECK (segment_number > 0),
    started_at          TIMESTAMPTZ,
    ended_at            TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (question_period_id, segment_number)
);

CREATE INDEX IF NOT EXISTS idx_congress_questioner_period
    ON congress_events.congress_questioner (question_period_id);

-- ============================================================
-- congress_score — one scorer's score for one speech
-- ============================================================
CREATE TABLE IF NOT EXISTS congress_events.congress_score (
    id          BIGSERIAL PRIMARY KEY,
    speech_id   BIGINT NOT NULL REFERENCES congress_events.congress_speech(id) ON DELETE CASCADE,
    scorer_id   INTEGER NOT NULL,
    points      INTEGER NOT NULL,
    feedback    TEXT,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (speech_id, scorer_id)
);

CREATE INDEX IF NOT EXISTS idx_congress_score_scorer
    ON congress_events.congress_score (scorer_id);

-- ============================================================
-- congress_ranking — end-of-session holistic ranking by one scorer
-- ============================================================
CREATE TABLE IF NOT EXISTS congress_events.congress_ranking (
    id                          BIGSERIAL PRIMARY KEY,
    session_id                  BIGINT NOT NULL REFERENCES congress_events.congress_session(id) ON DELETE CASCADE,
    scorer_id                   INTEGER NOT NULL,
    legislator_id               BIGINT NOT NULL REFERENCES congress_events.congress_legislator(id) ON DELETE CASCADE,
    rank_position               INTEGER NOT NULL CHECK (rank_position > 0),
    is_parliamentarian_ranking  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_congress_ranking_scorer_pos
    ON congress_events.congress_ranking (session_id, scorer_id, rank_position)
    WHERE NOT is_parliamentarian_ranking;
CREATE UNIQUE INDEX IF NOT EXISTS idx_congress_ranking_parl_pos
    ON congress_events.congress_ranking (session_id, scorer_id, rank_position)
    WHERE is_parliamentarian_ranking;
CREATE INDEX IF NOT EXISTS idx_congress_ranking_session
    ON congress_events.congress_ranking (session_id);
CREATE INDEX IF NOT EXISTS idx_congress_ranking_legislator
    ON congress_events.congress_ranking (legislator_id);

-- ============================================================
-- congress_po_election — PO election for a session
-- ============================================================
CREATE TABLE IF NOT EXISTS congress_events.congress_po_election (
    id                      BIGSERIAL PRIMARY KEY,
    session_id              BIGINT NOT NULL REFERENCES congress_events.congress_session(id) ON DELETE CASCADE,
    round_number            INTEGER NOT NULL DEFAULT 1 CHECK (round_number > 0),
    status                  congress_events.election_status NOT NULL DEFAULT 'OPEN',
    winner_legislator_id    BIGINT REFERENCES congress_events.congress_legislator(id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, round_number)
);

CREATE INDEX IF NOT EXISTS idx_congress_po_election_session
    ON congress_events.congress_po_election (session_id);

-- ============================================================
-- congress_po_ballot — one vote in a PO election
-- ============================================================
CREATE TABLE IF NOT EXISTS congress_events.congress_po_ballot (
    id                      BIGSERIAL PRIMARY KEY,
    election_id             BIGINT NOT NULL REFERENCES congress_events.congress_po_election(id) ON DELETE CASCADE,
    voter_legislator_id     BIGINT NOT NULL REFERENCES congress_events.congress_legislator(id) ON DELETE CASCADE,
    candidate_legislator_id BIGINT NOT NULL REFERENCES congress_events.congress_legislator(id) ON DELETE CASCADE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (election_id, voter_legislator_id)
);

CREATE INDEX IF NOT EXISTS idx_congress_po_ballot_election
    ON congress_events.congress_po_ballot (election_id);

-- ============================================================
-- congress_po_score — scorer's score for PO service per hour
-- ============================================================
CREATE TABLE IF NOT EXISTS congress_events.congress_po_score (
    id          BIGSERIAL PRIMARY KEY,
    session_id  BIGINT NOT NULL REFERENCES congress_events.congress_session(id) ON DELETE CASCADE,
    scorer_id   INTEGER NOT NULL,
    hour_number INTEGER NOT NULL CHECK (hour_number > 0),
    points      INTEGER NOT NULL,
    feedback    TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, scorer_id, hour_number)
);

-- ============================================================
-- congress_amendment — proposed amendment to legislation
-- ============================================================
CREATE TABLE IF NOT EXISTS congress_events.congress_amendment (
    id                          BIGSERIAL PRIMARY KEY,
    docket_item_id              BIGINT NOT NULL REFERENCES congress_events.congress_docket_item(id) ON DELETE CASCADE,
    submitted_by_legislator_id  BIGINT NOT NULL REFERENCES congress_events.congress_legislator(id) ON DELETE CASCADE,
    amendment_text              TEXT NOT NULL,
    status                      congress_events.amendment_status NOT NULL DEFAULT 'SUBMITTED',
    reviewed_at                 TIMESTAMPTZ,
    is_germane                  BOOLEAN,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_congress_amendment_docket
    ON congress_events.congress_amendment (docket_item_id);
CREATE INDEX IF NOT EXISTS idx_congress_amendment_status
    ON congress_events.congress_amendment (status);

-- ============================================================
-- congress_precedence_state — snapshot of current precedence queue
-- ============================================================
CREATE TABLE IF NOT EXISTS congress_events.congress_precedence_state (
    id              BIGSERIAL PRIMARY KEY,
    session_id      BIGINT NOT NULL REFERENCES congress_events.congress_session(id) ON DELETE CASCADE,
    legislator_id   BIGINT NOT NULL REFERENCES congress_events.congress_legislator(id) ON DELETE CASCADE,
    speech_count    INTEGER NOT NULL DEFAULT 0,
    last_speech_at  TIMESTAMPTZ,
    question_count  INTEGER NOT NULL DEFAULT 0,
    last_question_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, legislator_id)
);

CREATE INDEX IF NOT EXISTS idx_congress_precedence_session
    ON congress_events.congress_precedence_state (session_id);

-- ============================================================
-- Trigger function to auto-update updated_at
-- ============================================================
CREATE OR REPLACE FUNCTION congress_events.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at trigger to all tables
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOR tbl IN
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'congress_events'
          AND table_type = 'BASE TABLE'
    LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%s_updated_at
             BEFORE UPDATE ON congress_events.%I
             FOR EACH ROW EXECUTE FUNCTION congress_events.update_updated_at()',
            tbl, tbl
        );
    END LOOP;
END $$;
