# nekocongress — Congressional Debate Module Architecture

## PART 0 — Research Confirmation

### Codebase patterns confirmed:
- **FastAPI app structure** (nekospeech/main.py): Lifespan context manager for startup/shutdown, CORS middleware, router registration, health endpoint at `/api/{service}/health`
- **Settings pattern** (config.py): pydantic-settings BaseSettings with env_prefix, Heroku fallbacks for DATABASE_URL, REDIS_URL, DJANGO_SECRET_KEY, auto-converts postgres:// to postgresql+asyncpg://
- **Auth pattern** (auth.py): JWT shared with Django, role-based deps (require_director, require_judge), tournament-scoped via `verify_tournament_access`
- **Database pattern** (database.py): async SQLAlchemy with asyncpg, pool_size=2/max_overflow=2 for Heroku, get_db dependency
- **Shared models** (models/shared.py): Read-only SQLAlchemy Table objects mapped to Django's public schema tables
- **Router pattern** (routers/draw.py): APIRouter with prefix/tags, advisory locks, idempotent operations, cache invalidation
- **WebSocket** (websocket/manager.py): In-memory dict keyed by tournament_id — acknowledged as single-replica only. nekocongress MUST improve this with Redis pub/sub.
- **Heroku deploy** (Procfile): `web: uvicorn` + `worker: celery`
- **DB migrations** (001_create_speech_events_schema.sql): Raw SQL in migrations/ folder, CREATE SCHEMA IF NOT EXISTS, custom ENUMs, explicit indexes
- **Vue components** (templates/ie/): Vue 2 SFCs with Bootstrap 4 classes, data passed via window.vueData, kebab-case registration in main.js
- **Django views** (speech_events/views.py): TemplateView + AdministratorMixin + TournamentMixin, issue JWT tokens in context

---

## PART 1 — Architectural Decisions

### 1.1 Service Name and Placement

**Decision:** `nekocongress/` at repo root, mirroring nekospeech's structure exactly.

```
nekocongress/
├── nekocongress/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app entry
│   ├── config.py                   # pydantic-settings config
│   ├── auth.py                     # JWT auth (shared with Django)
│   ├── database.py                 # Async SQLAlchemy engine
│   ├── models/
│   │   ├── __init__.py
│   │   ├── shared.py               # Read-only Django table mappings
│   │   └── congress.py             # Congress schema tables
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── tournament.py
│   │   ├── chamber.py
│   │   ├── legislator.py
│   │   ├── legislation.py
│   │   ├── session.py
│   │   ├── floor.py
│   │   ├── score.py
│   │   ├── amendment.py
│   │   └── standings.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── tournaments.py
│   │   ├── chambers.py
│   │   ├── legislators.py
│   │   ├── docket.py
│   │   ├── sessions.py
│   │   ├── floor.py
│   │   ├── scores.py
│   │   ├── amendments.py
│   │   ├── standings.py
│   │   └── ws.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── precedence.py           # PrecedenceQueue engine
│   │   ├── po_election.py          # Instant-runoff PO election
│   │   ├── standings_engine.py     # Cross-chamber standings calc
│   │   ├── cache.py                # Redis cache helpers
│   │   └── normalization.py        # Z-score / percentile normalization
│   ├── websocket/
│   │   ├── __init__.py
│   │   ├── redis_manager.py        # Redis pub/sub channel manager
│   │   └── events.py               # WebSocket event type definitions
│   ├── workers/
│   │   ├── __init__.py
│   │   └── tasks.py                # Celery tasks
│   └── tests/
│       ├── __init__.py
│       ├── test_precedence.py      # PrecedenceQueue unit tests
│       ├── test_po_election.py     # PO election unit tests
│       └── test_standings.py       # Standings engine tests
├── migrations/
│   └── 001_create_congress_events_schema.sql
├── Procfile                        # Heroku subtree deploy
├── runtime.txt
├── requirements.txt
└── README.md
```

**Justification:** Identical structure to nekospeech enables:
- Same subtree deploy workflow to Heroku
- Familiar patterns for any developer who knows nekospeech
- Shared Postgres and Redis infrastructure
- Same JWT auth mechanism

### 1.2 Database Schema Design

Schema: `congress_events` (parallels `speech_events`)

All tables use BIGSERIAL PRIMARY KEY, created_at, updated_at as mandated.

#### Table: congress_tournament

Tournament-level configuration for Congressional Debate.

| Column | Type | Constraints | Justification |
|--------|------|-------------|---------------|
| id | BIGSERIAL | PRIMARY KEY | Standard |
| tournament_id | INTEGER NOT NULL | FK to public.tournaments_tournament | Links to Django tournament |
| name | VARCHAR(200) NOT NULL | | Display name for congress configuration |
| scoring_range_min | INTEGER NOT NULL DEFAULT 1 | CHECK (>= 0) | Low end of speech score range (1 for NSDA, 3 for Nationals) |
| scoring_range_max | INTEGER NOT NULL DEFAULT 8 | CHECK (<= 10) | High end of speech score range (8 for NSDA, 9 for Nationals) |
| po_scoring_range_min | INTEGER NOT NULL DEFAULT 1 | | PO score range low |
| po_scoring_range_max | INTEGER NOT NULL DEFAULT 8 | | PO score range high |
| top_n_ranking | INTEGER NOT NULL DEFAULT 8 | | How many legislators scorers rank at end of session |
| overtime_grace_seconds | INTEGER NOT NULL DEFAULT 10 | | Seconds past 3:00 before penalty starts |
| overtime_penalty_per_interval | INTEGER NOT NULL DEFAULT 1 | | Points deducted per overtime interval |
| overtime_interval_seconds | INTEGER NOT NULL DEFAULT 10 | | Interval length for overtime penalty calculation |
| wrong_side_penalty | INTEGER NOT NULL DEFAULT 3 | | Points deducted for speaking on wrong side |
| speech_time_seconds | INTEGER NOT NULL DEFAULT 180 | | Standard speech time (3 min) |
| authorship_speech_time_seconds | INTEGER NOT NULL DEFAULT 180 | | Authorship speech time |
| questioning_time_seconds | INTEGER NOT NULL DEFAULT 60 | | Standard questioning period (1 min) |
| authorship_questioning_time_seconds | INTEGER NOT NULL DEFAULT 120 | | Authorship questioning (2 min) |
| questioner_segment_seconds | INTEGER NOT NULL DEFAULT 30 | | Each questioner gets 30s |
| direct_questioning_enabled | BOOLEAN NOT NULL DEFAULT TRUE | | Whether direct questioning is allowed |
| geography_tiebreak_enabled | BOOLEAN NOT NULL DEFAULT FALSE | | Use geography for precedence tiebreak |
| advancement_method | VARCHAR(20) NOT NULL DEFAULT 'COMBINED' | ENUM | POINTS, RANKINGS, COMBINED |
| normalization_method | VARCHAR(20) NOT NULL DEFAULT 'ZSCORE' | ENUM | ZSCORE, PERCENTILE for cross-chamber comparison |
| num_preliminary_sessions | INTEGER NOT NULL DEFAULT 3 | | Number of prelim sessions |
| num_elimination_sessions | INTEGER NOT NULL DEFAULT 2 | | Semifinal + final |
| chamber_size_target | INTEGER NOT NULL DEFAULT 18 | | NSDA recommended chamber size |
| is_active | BOOLEAN NOT NULL DEFAULT TRUE | | Soft delete |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT NOW() | | |
| updated_at | TIMESTAMPTZ NOT NULL DEFAULT NOW() | | |

**Indexes:** `idx_congress_tournament_tid` on (tournament_id), UNIQUE on (tournament_id) — one congress config per tournament.

#### Table: congress_chamber

| Column | Type | Constraints | Justification |
|--------|------|-------------|---------------|
| id | BIGSERIAL | PRIMARY KEY | |
| congress_tournament_id | BIGINT NOT NULL | FK → congress_tournament | Parent tournament config |
| label | VARCHAR(100) NOT NULL | | e.g. "House 1", "Senate A" |
| chamber_type | VARCHAR(10) NOT NULL DEFAULT 'HOUSE' | HOUSE/SENATE | Naming convention |
| chamber_number | INTEGER NOT NULL | | Ordering within tournament |
| is_elimination | BOOLEAN NOT NULL DEFAULT FALSE | | Is this a semifinal/final chamber? |
| created_at/updated_at | TIMESTAMPTZ | | |

**Indexes:** UNIQUE on (congress_tournament_id, chamber_number). Index on congress_tournament_id.

#### Table: congress_session

| Column | Type | Constraints | Justification |
|--------|------|-------------|---------------|
| id | BIGSERIAL | PRIMARY KEY | |
| chamber_id | BIGINT NOT NULL | FK → congress_chamber | Which chamber |
| session_number | INTEGER NOT NULL | | 1, 2, 3 for prelim sessions |
| status | VARCHAR(20) NOT NULL DEFAULT 'PENDING' | | PENDING/ACTIVE/CLOSED |
| po_legislator_id | BIGINT NULL | FK → congress_legislator | Elected PO |
| session_duration_minutes | INTEGER NOT NULL DEFAULT 150 | | 2.5 hours standard |
| started_at | TIMESTAMPTZ NULL | | When session actually started |
| closed_at | TIMESTAMPTZ NULL | | When session was closed |
| current_legislation_id | BIGINT NULL | FK → congress_docket_item | Currently being debated |
| current_speech_number | INTEGER NOT NULL DEFAULT 0 | | Speech count on current legislation |
| next_side | VARCHAR(3) NOT NULL DEFAULT 'AFF' | AFF/NEG | Which side should speak next |
| created_at/updated_at | TIMESTAMPTZ | | |

**Indexes:** UNIQUE on (chamber_id, session_number). Index on chamber_id, status.

#### Table: congress_legislator

| Column | Type | Constraints | Justification |
|--------|------|-------------|---------------|
| id | BIGSERIAL | PRIMARY KEY | |
| congress_tournament_id | BIGINT NOT NULL | FK → congress_tournament | Tournament link |
| speaker_id | INTEGER NOT NULL | FK → participants_speaker | Links to Django participant |
| display_name | VARCHAR(200) NOT NULL | | Cached for performance |
| institution_id | INTEGER NULL | | Denormalized from speaker |
| institution_code | VARCHAR(20) NULL | | Denormalized for display |
| is_withdrawn | BOOLEAN NOT NULL DEFAULT FALSE | | Soft withdrawal |
| created_at/updated_at | TIMESTAMPTZ | | |

**Indexes:** UNIQUE on (congress_tournament_id, speaker_id). Index on congress_tournament_id.

#### Table: congress_chamber_assignment

| Column | Type | Constraints | Justification |
|--------|------|-------------|---------------|
| id | BIGSERIAL | PRIMARY KEY | |
| chamber_id | BIGINT NOT NULL | FK → congress_chamber | |
| legislator_id | BIGINT NOT NULL | FK → congress_legislator | |
| seat_number | INTEGER NULL | | Optional seating position |
| created_at/updated_at | TIMESTAMPTZ | | |

**Indexes:** UNIQUE on (chamber_id, legislator_id). Index on legislator_id.

#### Table: congress_legislation

| Column | Type | Constraints | Justification |
|--------|------|-------------|---------------|
| id | BIGSERIAL | PRIMARY KEY | |
| congress_tournament_id | BIGINT NOT NULL | FK → congress_tournament | |
| title | VARCHAR(500) NOT NULL | | Bill/resolution title |
| legislation_type | VARCHAR(15) NOT NULL | BILL/RESOLUTION | |
| category | VARCHAR(50) NULL | | Economics, Foreign Affairs, etc. |
| author_institution_id | INTEGER NULL | | School that authored it |
| full_text | TEXT NULL | | Full text of the legislation |
| docket_code | VARCHAR(20) NOT NULL | | e.g. "B-1", "R-3" |
| created_at/updated_at | TIMESTAMPTZ | | |

**Indexes:** UNIQUE on (congress_tournament_id, docket_code). Index on congress_tournament_id.

#### Table: congress_docket_item

| Column | Type | Constraints | Justification |
|--------|------|-------------|---------------|
| id | BIGSERIAL | PRIMARY KEY | |
| session_id | BIGINT NOT NULL | FK → congress_session | |
| legislation_id | BIGINT NOT NULL | FK → congress_legislation | |
| agenda_order | INTEGER NOT NULL | | Position in session's agenda |
| status | VARCHAR(20) NOT NULL DEFAULT 'PENDING' | | PENDING/DEBATING/VOTED/TABLED/CARRIED_OVER |
| vote_result | VARCHAR(10) NULL | | PASS/FAIL/TABLED |
| aff_votes | INTEGER NULL | | Vote count |
| neg_votes | INTEGER NULL | | |
| abstain_votes | INTEGER NULL | | |
| created_at/updated_at | TIMESTAMPTZ | | |

**Indexes:** UNIQUE on (session_id, agenda_order). Index on session_id, legislation_id.

#### Table: congress_speech

| Column | Type | Constraints | Justification |
|--------|------|-------------|---------------|
| id | BIGSERIAL | PRIMARY KEY | |
| session_id | BIGINT NOT NULL | FK → congress_session | |
| docket_item_id | BIGINT NOT NULL | FK → congress_docket_item | Which legislation |
| legislator_id | BIGINT NOT NULL | FK → congress_legislator | Who spoke |
| speech_number | INTEGER NOT NULL | | Nth speech on this legislation |
| session_speech_number | INTEGER NOT NULL | | Nth speech in entire session (for precedence) |
| side | VARCHAR(10) NOT NULL | AFF/NEG/AUTHORSHIP/SPONSORSHIP | |
| speech_type | VARCHAR(15) NOT NULL DEFAULT 'STANDARD' | AUTHORSHIP/SPONSORSHIP/STANDARD | |
| started_at | TIMESTAMPTZ NULL | | Server-recorded start time |
| ended_at | TIMESTAMPTZ NULL | | Server-recorded end time |
| duration_seconds | INTEGER NULL | | Calculated duration |
| is_overtime | BOOLEAN NOT NULL DEFAULT FALSE | | Exceeded time limit |
| overtime_seconds | INTEGER NOT NULL DEFAULT 0 | | How much over |
| overtime_penalty | INTEGER NOT NULL DEFAULT 0 | | Calculated penalty points |
| wrong_side | BOOLEAN NOT NULL DEFAULT FALSE | | Spoke on wrong side |
| wrong_side_penalty | INTEGER NOT NULL DEFAULT 0 | | –3 typically |
| created_at/updated_at | TIMESTAMPTZ | | |

**Indexes:** Index on (session_id, legislator_id), (session_id, speech_number), docket_item_id.

#### Table: congress_question_period

| Column | Type | Constraints | Justification |
|--------|------|-------------|---------------|
| id | BIGSERIAL | PRIMARY KEY | |
| speech_id | BIGINT NOT NULL | FK → congress_speech | After which speech |
| total_time_seconds | INTEGER NOT NULL | | 60 or 120 for authorship |
| started_at | TIMESTAMPTZ NULL | | |
| ended_at | TIMESTAMPTZ NULL | | |
| created_at/updated_at | TIMESTAMPTZ | | |

**Indexes:** UNIQUE on speech_id (one questioning period per speech).

#### Table: congress_questioner

| Column | Type | Constraints | Justification |
|--------|------|-------------|---------------|
| id | BIGSERIAL | PRIMARY KEY | |
| question_period_id | BIGINT NOT NULL | FK → congress_question_period | |
| legislator_id | BIGINT NOT NULL | FK → congress_legislator | Who questioned |
| segment_number | INTEGER NOT NULL | | 1st, 2nd, etc. questioner |
| started_at | TIMESTAMPTZ NULL | | |
| ended_at | TIMESTAMPTZ NULL | | |
| created_at/updated_at | TIMESTAMPTZ | | |

**Indexes:** Index on question_period_id. UNIQUE on (question_period_id, segment_number).

#### Table: congress_score

| Column | Type | Constraints | Justification |
|--------|------|-------------|---------------|
| id | BIGSERIAL | PRIMARY KEY | |
| speech_id | BIGINT NOT NULL | FK → congress_speech | |
| scorer_id | INTEGER NOT NULL | | FK → participants_adjudicator loosely |
| points | INTEGER NOT NULL | | Within tournament's scoring range |
| feedback | TEXT NULL | | Written feedback per speech |
| submitted_at | TIMESTAMPTZ NOT NULL DEFAULT NOW() | | |
| created_at/updated_at | TIMESTAMPTZ | | |

**Indexes:** UNIQUE on (speech_id, scorer_id). Index on scorer_id.

#### Table: congress_ranking

| Column | Type | Constraints | Justification |
|--------|------|-------------|---------------|
| id | BIGSERIAL | PRIMARY KEY | |
| session_id | BIGINT NOT NULL | FK → congress_session | |
| scorer_id | INTEGER NOT NULL | | Who ranked |
| legislator_id | BIGINT NOT NULL | FK → congress_legislator | Who was ranked |
| rank_position | INTEGER NOT NULL | | 1-8 (or full for parliamentarian) |
| is_parliamentarian_ranking | BOOLEAN NOT NULL DEFAULT FALSE | | Parliamentarian vs scorer |
| created_at/updated_at | TIMESTAMPTZ | | |

**Indexes:** UNIQUE on (session_id, scorer_id, rank_position) for scorer rankings. Index on session_id, legislator_id.

#### Table: congress_po_election

| Column | Type | Constraints | Justification |
|--------|------|-------------|---------------|
| id | BIGSERIAL | PRIMARY KEY | |
| session_id | BIGINT NOT NULL | FK → congress_session | |
| round_number | INTEGER NOT NULL DEFAULT 1 | | IRV round |
| status | VARCHAR(20) NOT NULL DEFAULT 'OPEN' | OPEN/ELIMINATED/DECIDED | |
| winner_legislator_id | BIGINT NULL | FK → congress_legislator | |
| created_at/updated_at | TIMESTAMPTZ | | |

**Indexes:** UNIQUE on (session_id, round_number). Index on session_id.

#### Table: congress_po_ballot

| Column | Type | Constraints | Justification |
|--------|------|-------------|---------------|
| id | BIGSERIAL | PRIMARY KEY | |
| election_id | BIGINT NOT NULL | FK → congress_po_election | |
| voter_legislator_id | BIGINT NOT NULL | FK → congress_legislator | Anonymous but tracked |
| candidate_legislator_id | BIGINT NOT NULL | FK → congress_legislator | Who they voted for |
| created_at/updated_at | TIMESTAMPTZ | | |

**Indexes:** UNIQUE on (election_id, voter_legislator_id). Index on election_id.

#### Table: congress_po_score

| Column | Type | Constraints | Justification |
|--------|------|-------------|---------------|
| id | BIGSERIAL | PRIMARY KEY | |
| session_id | BIGINT NOT NULL | FK → congress_session | |
| scorer_id | INTEGER NOT NULL | | Who scored the PO |
| hour_number | INTEGER NOT NULL | | Which hour of presiding |
| points | INTEGER NOT NULL | | Within tournament's PO scoring range |
| feedback | TEXT NULL | | |
| created_at/updated_at | TIMESTAMPTZ | | |

**Indexes:** UNIQUE on (session_id, scorer_id, hour_number).

#### Table: congress_amendment

| Column | Type | Constraints | Justification |
|--------|------|-------------|---------------|
| id | BIGSERIAL | PRIMARY KEY | |
| docket_item_id | BIGINT NOT NULL | FK → congress_docket_item | Which legislation |
| submitted_by_legislator_id | BIGINT NOT NULL | FK → congress_legislator | |
| amendment_text | TEXT NOT NULL | | The amendment text |
| status | VARCHAR(20) NOT NULL DEFAULT 'SUBMITTED' | SUBMITTED/ACCEPTED/REJECTED/DEBATED/WITHDRAWN | |
| reviewed_at | TIMESTAMPTZ NULL | | When parliamentarian reviewed |
| is_germane | BOOLEAN NULL | | Parliamentarian's determination |
| created_at/updated_at | TIMESTAMPTZ | | |

**Indexes:** Index on docket_item_id, status.

#### Table: congress_precedence_state

| Column | Type | Constraints | Justification |
|--------|------|-------------|---------------|
| id | BIGSERIAL | PRIMARY KEY | |
| session_id | BIGINT NOT NULL | FK → congress_session | |
| legislator_id | BIGINT NOT NULL | FK → congress_legislator | |
| speech_count | INTEGER NOT NULL DEFAULT 0 | | Speeches given in session |
| last_speech_at | TIMESTAMPTZ NULL | | When they last spoke |
| question_count | INTEGER NOT NULL DEFAULT 0 | | Questions asked in session |
| last_question_at | TIMESTAMPTZ NULL | | When they last questioned |
| created_at/updated_at | TIMESTAMPTZ | | |

**Indexes:** UNIQUE on (session_id, legislator_id). Index on session_id.

### 1.3 PrecedenceQueue Design

See `nekocongress/nekocongress/services/precedence.py` for complete implementation.

The algorithm implements NSDA's 3-tier priority:
1. **Tier 1:** Students who have NOT spoken this session (tied → geography, then random)
2. **Tier 2:** Students who have spoken FEWER TIMES this session
3. **Tier 3:** Students who spoke LEAST RECENTLY this session (oldest speech first)

Questioner queue tracked completely separately with same 3-tier logic.

State persisted to Redis for crash recovery, reconstructible from database for disaster recovery.

### 1.4 WebSocket Architecture with Redis Pub/Sub

See `nekocongress/nekocongress/websocket/redis_manager.py` for complete implementation.

**Architecture:**
- Each chamber gets a Redis channel: `congress:chamber:{chamber_id}:events`
- Director gets aggregated channel: `congress:director:{tournament_id}:events`
- All nekocongress replicas subscribe to relevant channels on WebSocket connect
- Events published to Redis are fanned out to all replicas → all connected clients
- Typed events with Pydantic models for type safety

---

## PART 2 — Complete API Design

### Router: /api/congress/tournaments/

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | / | Director | Create congress tournament configuration |
| GET | /?tournament_id={id} | Director | List congress configs for a tournament |
| GET | /{id}/ | Director | Get configuration detail |
| PATCH | /{id}/ | Director | Update configuration |

### Router: /api/congress/chambers/

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | / | Director | Create chamber |
| GET | /?tournament_id={id} | Director | List chambers |
| GET | /{id}/ | Director | Chamber detail with sessions |
| POST | /{id}/assign-legislators/ | Director | Bulk assign legislators |
| GET | /{id}/seating-chart/ | Any | Current seating arrangement |

### Router: /api/congress/legislators/

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | / | Director | Register legislator |
| POST | /bulk/ | Director | Bulk register |
| GET | /?tournament_id={id} | Any | List all legislators |
| DELETE | /{id}/ | Director | Withdraw (soft delete) |

### Router: /api/congress/docket/

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /legislation/ | Director | Upload legislation |
| GET | /legislation/?tournament_id | Any | List legislation |
| PATCH | /legislation/{id}/ | Director | Edit metadata |
| POST | /assign/ | Director | Assign legislation to session |
| GET | /session/{session_id}/ | Any | Get session docket |
| PATCH | /session/{session_id}/reorder/ | Director | Reorder agenda |

### Router: /api/congress/sessions/

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | / | Director | Create session |
| GET | /{id}/ | Any | Session detail with full state |
| POST | /{id}/start/ | Director | Start session |
| POST | /{id}/close/ | Director | Close session |
| POST | /{id}/elect-po/ | Any (voter) | Submit PO election ballot |
| GET | /{id}/po-election/ | Any | Current election tally |
| POST | /{id}/confirm-po/ | Director | Confirm elected PO |
| GET | /{id}/precedence/ | Any | Current speaker queue |
| GET | /{id}/questioner-queue/ | Any | Current questioner queue |

### Router: /api/congress/floor/

| Method | Path | Auth | WS Events | Description |
|--------|------|------|-----------|-------------|
| POST | /recognize-speaker/ | PO/Director | SPEAKER_RECOGNIZED, QUEUE_UPDATED | Recognize next speaker |
| POST | /start-speech/ | PO/Director | SPEECH_STARTED, TIMER_TICK | Speech begins |
| POST | /end-speech/ | PO/Director | SPEECH_ENDED, QUEUE_UPDATED | Speech ends |
| POST | /open-questions/ | PO/Director | QUESTIONS_OPENED | Open questioning |
| POST | /recognize-questioner/ | PO/Director | QUESTIONER_RECOGNIZED | Recognize questioner |
| POST | /close-questions/ | PO/Director | QUESTIONS_CLOSED | Close questioning |
| POST | /change-legislation/ | PO/Director | LEGISLATION_CHANGED | Move to next item |
| POST | /call-vote/ | PO/Director | VOTE_CALLED | Initiate vote |
| POST | /record-vote/ | PO/Director | VOTE_RECORDED | Record vote result |

### Router: /api/congress/scores/

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /speech/ | Judge | Submit speech score |
| PATCH | /speech/{id}/ | Judge | Edit score (before session close) |
| POST | /ranking/ | Judge | Submit end-of-session top-N ranking |
| POST | /parliamentarian-ranking/ | Judge | Parliamentarian full ranking |
| POST | /po/ | Judge | Submit PO score per hour |
| GET | /session/{session_id}/ | Director | All scores for session |

### Router: /api/congress/amendments/

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | / | Any (legislator) | Submit amendment |
| GET | /?session_id={id} | Any | List amendments for session |
| POST | /{id}/review/ | Director/Parliamentarian | Accept/reject amendment |
| POST | /{id}/debate/ | PO/Director | Begin debate on amendment |

### Router: /api/congress/standings/

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /{tournament_id}/ | Any | Full standings |
| GET | /{tournament_id}/chamber/{id}/ | Any | Single chamber standings |
| GET | /{tournament_id}/advancement/ | Director | Advancement list |
| GET | /{tournament_id}/export/ | Director | CSV export |

### WebSocket: /api/congress/ws/

| Path | Auth | Description |
|------|------|-------------|
| /chamber/{chamber_id}/ | Any | Chamber participants |
| /director/{tournament_id}/ | Director | Bird's eye view of all chambers |
| /student/{legislator_id}/ | Student token | Personal queue position |
| /scorer/{session_id}/ | Judge | Live speech feed |

---

## PART 3 — UI/UX Design (Adjudicator-Centered)

### 3.1 Design Principles Summary

1. **Role-specific interfaces** — 5 different views for 5 different roles
2. **Zero friction** — Critical PO actions reachable in ONE tap
3. **Error prevention** — System makes wrong actions impossible
4. **Real-time** — All state changes within 500ms via Redis pub/sub WebSocket
5. **Offline resilience** — Local queue for scores, cached state for PO
6. **PO interface as marketing** — Seen by every student, must be branded + impressive

### 3.2 Nine Vue Components

See tabbycat/templates/congress/ directory for all component files.

1. **CongressSetupWizard.vue** — Multi-step tournament config wizard
2. **DocketManager.vue** — Legislation grid with drag-to-reorder
3. **ChamberAssignment.vue** — Legislator-to-chamber assignment with balance
4. **POElection.vue** — Instant-runoff voting interface
5. **LiveSessionFloor.vue** — THE PO interface (landscape tablet optimized)
6. **ScorerBallot.vue** — Mobile-first scoring (1-tap score entry)
7. **ParliamentarianPanel.vue** — Split view: mirror + tools
8. **CongressStandings.vue** — Post-session standings with export
9. **StudentSessionView.vue** — Student phone view (queue + recognition)

### 3.3 Visual Style

Matches Tabbycat exactly: Bootstrap 4, table-hover, table-sm, table-striped,
badge classes, card components, thead-light. Only additions are CSS keyframe
animations for timers and live indicators.

---

## PART 4 — 15-Phase Implementation Plan

| Phase | What | Verification |
|-------|------|-------------|
| P01 | Service scaffold + config | `uvicorn nekocongress.main:app` starts, /health returns ok |
| P02 | Database schema + migration SQL | Migration executes without error |
| P03 | SQLAlchemy models + shared models | Models import without error |
| P04 | All Pydantic schemas | Schemas instantiate with sample data |
| P05 | PrecedenceQueue with unit tests | All tests pass (18-legislator, 3-session scenarios) |
| P06 | PO election engine with tests | IRV algorithm tests pass |
| P07 | Tournament, chamber, legislator CRUD routers | curl POST/GET/PATCH work |
| P08 | Docket and legislation routers | Legislation CRUD + session assignment works |
| P09 | Session management routers | Start/close session, PO election flow works |
| P10 | Floor management routers | Recognize/speech/questions flow works end-to-end |
| P11 | Score and ranking submission | Score submission + edit + ranking works |
| P12 | Amendment engine | Submit/review/debate flow works |
| P13 | Standings and advancement engine | Standings calculation with normalization works |
| P14 | Redis pub/sub WebSocket system | Multi-client WebSocket with Redis fan-out works |
| P15 | Django wiring (views, URLs, templates, Vue) | Congress pages load in Tabbycat UI |

---

## PART 5 — Growth Engineering

| # | Feature | Mechanism | Cost | Priority |
|---|---------|-----------|------|----------|
| 1 | Student Session View (viral) | Every student sees NekoTab branding on their phone; shares naturally | Low | v1 |
| 2 | Scorer Feedback Retention | Judges who give feedback stick; students come back to see it | Low | v1 |
| 3 | Public Session Archive | Tournament results visible forever; SEO for NekoTab | Medium | v1 |
| 4 | Director Analytics Dashboard | Shows chamber performance; directors feel in control; renewal | Medium | v2 |
| 5 | Cross-Tournament Legislator Records | Student career history; builds loyalty; competitive drive | High | v2 |

---

## PART 6 — Self-Review

### As an Adjudicator:
- Precedence algorithm correctly implements NSDA 3-tier priority
- PO interface automates queue management — student PO just confirms
- Scoring range is fully configurable per tournament (1-8, 3-9, custom)
- Overtime and wrong-side penalties are configurable and auto-calculated
- Amendment process follows Robert's Rules (submit → review → debate)

### As a UX Designer:
- Scorer can score a speech in 5 taps (receive card → tap score → optional feedback → next)
- PO has all 5 critical actions in ONE tap from any state
- Offline queuing implemented via localStorage for scorers
- Auto-reconnect WebSocket with state catch-up

### As a Growth Engineer:
- NekoTab brand on every student's phone screen
- Path from student → "I want to use this as a director"
- Public archives create organic SEO traffic

### 3 Architecture Changes:
1. Add event sourcing for floor actions (every action as immutable event log for replay)
2. Add read replicas for standings queries under load
3. Consider gRPC between Django and nekocongress for internal calls instead of HTTP

### 3 UI Changes:
1. Add haptic feedback on mobile for score submission confirmation
2. Add dark mode for scorer interface (back-of-room, low light)
3. Add landscape lock prompt for PO interface on first load

### 2 Things Better Than Tabroom:
1. Real-time queue automation — Tabroom requires manual precedence tracking
2. Multi-device sync — Tabroom's Congress is paper-first with manual entry

### 1 Thing Tabroom Does That We Cannot Yet:
- Tabroom has 20+ years of historical data and cross-tournament NSDA point integration. Our cross-tournament records (Growth Feature #5) are v2.
