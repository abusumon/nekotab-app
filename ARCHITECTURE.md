# NekoTab — Application Architecture Specification
## Debate Tabulation Platform · v1.0

---

## Table of Contents

1. [Component Map](#1-component-map)
2. [Design Tokens](#2-design-tokens)
3. [Frontend Routes](#3-frontend-routes)
4. [Data Model](#4-data-model)
5. [RBAC Permissions](#5-rbac-permissions)
6. [API Endpoint Reference](#6-api-endpoint-reference)
7. [Overview Page State Flow](#7-overview-page-state-flow)
8. [Realtime WebSocket Events](#8-realtime-websocket-events)
9. [Error Handling Patterns](#9-error-handling-patterns)
10. [Auth Strategy](#10-auth-strategy)

---

## 1. Component Map

### Shared Layout

| Component | Description | Location |
|-----------|-------------|----------|
| `Header` | Sticky 52px bar: Logo (220px, matches sidebar), header tabs, round pill, bell icon, logout | `components/layout/Header.tsx` |
| `Sidebar` | 220px left rail: tournament context chip, nav groups (Tabulation/Setup for admin, Browse/Tabs/Actions for public), user chip footer | `components/layout/Sidebar.tsx` |
| `TournamentContextChip` | Shows tournament name, format, round count inside sidebar | `components/layout/TournamentContextChip.tsx` |
| `UserChip` | Avatar + name + role at sidebar bottom | `components/layout/UserChip.tsx` |
| `RoundPill` | Header right — "Round N · Status" with animated pip | `components/layout/RoundPill.tsx` |

### Overview Page (Tab Director)

| Component | Description | Data Source |
|-----------|-------------|-------------|
| `PageHeader` | Eyebrow label + title + meta tags + action buttons | `GET /overview` → `tournamentContext` |
| `StatsRow` | 4× `StatCard` grid: Teams, Judges, Rounds, Current | `GET /overview` → `stats` |
| `StatCard` | Label (mono 10px) + big number (mono 36px bold) + subtitle | Stats object field |
| `DrawPanel` | Full card: header, round tracker, motion strip, draw table, footer progress | `GET /overview` → `currentRound`, `roundTracker`, `currentMotion`, `currentDrawRooms`, `ballotSummary` |
| `RoundTracker` | Horizontal stepper: R1..R5 dots (done ✓ green / active ● violet / pending ○ gray) connected by lines | `roundTracker[]` |
| `MotionStrip` | MOTION label + text + Analyze button | `currentMotion` |
| `DrawTable` | Table: Room, OG, OO, CG, CO, Status chip (Done/Pending/Missing) | `currentDrawRooms[]` |
| `DrawFooter` | Progress bar + "N/M ballots · X%" | `ballotSummary` |
| `CompletionRing` | SVG donut (violet fill) + legend (submitted/pending/missing) | `ballotSummary` |
| `QuickActions` | List of 4 action items with icon, title, subtitle, arrow; enabled/disabled rules | `quickActions[]` |
| `CheckInWidget` | 3-column grid: Teams/Judges/Venues checked-in counts | `checkinSummary` |

### Overview Page (Public View)

| Component | Description | Data Source |
|-----------|-------------|-------------|
| `PageHeader` | Tournament name, org, location, dates, status chip | Context + content block |
| `StatsRow` | 4× `StatCard`: Teams, Judges, Rounds, Motions | Django context vars |
| `WelcomePanel` | Welcome message HTML | `pref.welcome_message` |
| `AboutPanel` | About text | `content_block.about_text` |
| `TournamentInfoPanel` | Nav list of all available public links (results, draws, motions, tabs, etc.) | Preferences-gated |
| `RoundProgressWidget` | SVG completion ring + completed/remaining counts | `ring_offset`, `completed_round_count` |
| `QuickLinksWidget` | Quick link items to results, draw, motions, participants, schedule | Preferences-gated |
| `HostCTA` | Call-to-action to create tournament | Static |

---

## 2. Design Tokens

### Typography (IBM Plex Mono Only)

```css
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:ital,wght@0,300;0,400;0,500;0,600;0,700;1,300;1,400;1,500;1,600;1,700&display=swap');

:root {
  /* SINGLE font family for the entire application */
  --mono: 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;

  /* REMOVED: --serif, --sans — no longer used */
}
```

#### Hierarchy via weight/size/spacing (NOT font family)

| Level | Size | Weight | Letter-spacing | Usage |
|-------|------|--------|----------------|-------|
| Display | 36px | 700 | -0.04em | Stat card numbers |
| H1 | 22px | 700 | -0.03em | Page title |
| H2 | 14px | 700 | 0 | Panel titles |
| H3 | 13px | 700 | 0 | Section labels |
| Body | 13.5px | 400-500 | 0 | Default text |
| Caption | 12px | 500 | 0 | Table cells, meta |
| Label | 10px | 600-700 | 0.10-0.14em | ALL CAPS labels |
| Micro | 9px | 600-700 | 0.12em | Eyebrow, group headers |
| Code | 11.5px | 600 | 0 | Buttons, pills, badges |

### Color Tokens

```css
:root {
  /* Surfaces */
  --bg:        #F0F2F8;
  --surface:   #FFFFFF;
  --surface-2: #F7F8FC;
  --surface-3: #EEF0F8;
  --border:    #E4E7F2;
  --border-2:  #D8DCF0;

  /* Brand (Violet) */
  --v:      #6366f1;
  --v-soft: rgba(99,102,241,.09);
  --v-mid:  rgba(99,102,241,.18);
  --v-text: #4f46e5;

  /* Neutrals */
  --ink:    #0F1020;
  --ink-2:  #2A2D48;
  --ink-3:  #5A5E80;
  --muted:  #9498BC;
  --ghost:  #C8CCE4;

  /* Status */
  --green:      #16A36A;
  --green-soft: rgba(22,163,106,.09);
  --amber:      #C98A00;
  --amber-soft: rgba(201,138,0,.09);
  --red:        #D63B5A;
  --red-soft:   rgba(214,59,90,.09);
}
```

### Geometry Tokens

```css
:root {
  --r-xs: 5px;
  --r-sm: 8px;
  --r-md: 12px;
  --r-lg: 16px;
  --r-xl: 22px;

  --sh-1: 0 1px 3px rgba(15,16,32,.05), 0 1px 2px rgba(15,16,32,.04);
  --sh-2: 0 3px 12px rgba(15,16,32,.07), 0 1px 4px rgba(15,16,32,.05);
  --sh-v: 0 4px 18px rgba(99,102,241,.22), 0 1px 4px rgba(99,102,241,.14);
}
```

---

## 3. Frontend Routes

### Public Routes

| Route | Page | Purpose | Required Data |
|-------|------|---------|---------------|
| `/t/:slug` | PublicTournamentIndex | Public overview dashboard | Tournament, stats, prefs, content_block, rounds |
| `/t/:slug/results` | PublicResults | Released round results | Released results list |
| `/t/:slug/draw` | PublicDraw | Current round draw | Current draw rooms, round info |
| `/t/:slug/motions` | PublicMotions | Released motions | Motions list |
| `/t/:slug/participants` | PublicParticipants | Teams & judges list | Teams, adjudicators |
| `/t/:slug/standings` | PublicStandings | Team standings | Standings data |
| `/t/:slug/tabs/:type` | PublicTab | Released tabs (team/speaker/adj) | Tab data by type |
| `/t/:slug/breaks/:category` | PublicBreaks | Break results | Break category data |

### Tab Director (Admin) Routes

| Route | Page | Purpose | Required Data |
|-------|------|---------|---------------|
| `/tournaments/:id/overview` | DirectorOverview | Full dashboard with stats, draw, widgets | `GET /overview` aggregate |
| `/tournaments/:id/draws` | DirectorDraws | Manage draws for all rounds | Rounds list, current draw |
| `/tournaments/:id/draws/:roundId` | DirectorDrawDetail | Single round draw management | Draw rooms, allocations |
| `/tournaments/:id/allocations` | DirectorAllocations | Judge allocation for current round | Allocations, judges, rooms |
| `/tournaments/:id/ballots` | DirectorBallots | Ballot entry/review for current round | Ballots list, rooms |
| `/tournaments/:id/ballots/:roundId` | DirectorBallotsRound | Ballots for specific round | Round ballots |
| `/tournaments/:id/standings` | DirectorStandings | Live standings computation | Standings snapshot |
| `/tournaments/:id/results` | DirectorResults | Released results management | Results data |
| `/tournaments/:id/breaks` | DirectorBreaks | Break computation & publication | Break categories, teams |
| `/tournaments/:id/setup/teams` | SetupTeams | CRUD teams | Teams list |
| `/tournaments/:id/setup/judges` | SetupJudges | CRUD judges, check-in | Judges list |
| `/tournaments/:id/setup/venues` | SetupVenues | CRUD venues, check-in | Venues list |
| `/tournaments/:id/setup/settings` | SetupSettings | Tournament configuration | Preferences object |

---

## 4. Data Model

### Entity Relationship Diagram (Text)

```
User ─┬── TournamentMembership ──┬── Tournament
      │                          │
      │                          ├── Team ──── Speaker[]
      │                          ├── Judge
      │                          ├── Venue
      │                          ├── Round ──┬── Room ──┬── DrawSeat (position: OG|OO|CG|CO → teamId)
      │                          │           │         ├── Allocation (judgeId, role)
      │                          │           │         └── Ballot (status, scores, notes)
      │                          │           └── Motion
      │                          ├── StandingSnapshot
      │                          └── BreakCategory ── BreakTeam
      │
      └── Notification
```

### Table Definitions

#### `User`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `email` | VARCHAR(255) | Unique, login |
| `name` | VARCHAR(255) | Display name |
| `password_hash` | TEXT | bcrypt/argon2 |
| `is_superuser` | BOOLEAN | Global admin |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

#### `Tournament`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `name` | VARCHAR(255) | |
| `short_name` | VARCHAR(50) | |
| `slug` | VARCHAR(100) | Unique, URL-safe |
| `format` | ENUM | `bp`, `australs`, `wsdc`, `asian`, `custom` |
| `timezone` | VARCHAR(50) | IANA timezone |
| `total_rounds` | INT | Planned rounds |
| `active` | BOOLEAN | Is tournament live |
| `created_by` | UUID FK → User | |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

#### `TournamentMembership`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `user_id` | UUID FK → User | |
| `tournament_id` | UUID FK → Tournament | |
| `role` | ENUM | `admin`, `tabber`, `runner`, `viewer` |
| **Unique** | `(user_id, tournament_id)` | |

#### `Team`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `tournament_id` | UUID FK → Tournament | |
| `name` | VARCHAR(255) | |
| `short_name` | VARCHAR(50) | |
| `institution` | VARCHAR(255) | |
| `emoji` | VARCHAR(10) | Optional identifier |
| `speakers` | JSONB | `[{name, email}]` |
| `checked_in` | BOOLEAN | |
| `active` | BOOLEAN | |
| `created_at` | TIMESTAMP | |

#### `Judge`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `tournament_id` | UUID FK → Tournament | |
| `name` | VARCHAR(255) | |
| `institution` | VARCHAR(255) | |
| `email` | VARCHAR(255) | |
| `checked_in` | BOOLEAN | |
| `rank` | INT | 0-100 quality score |
| `is_independent` | BOOLEAN | No institutional conflict |
| `active` | BOOLEAN | |
| `created_at` | TIMESTAMP | |

#### `Venue`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `tournament_id` | UUID FK → Tournament | |
| `name` | VARCHAR(255) | |
| `capacity` | INT | |
| `checked_in` | BOOLEAN | |
| `priority` | INT | Higher → preferred |
| `active` | BOOLEAN | |
| `created_at` | TIMESTAMP | |

#### `Round`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `tournament_id` | UUID FK → Tournament | |
| `seq` | INT | Round sequence number |
| `name` | VARCHAR(50) | e.g. "Round 1" |
| `abbreviation` | VARCHAR(10) | e.g. "R1" |
| `status` | ENUM | `draft`, `active`, `completed` |
| `motion_text` | TEXT | Current round motion |
| `info_slide` | TEXT | Pre-motion info |
| `draw_status` | ENUM | `none`, `draft`, `confirmed`, `released` |
| `starts_at` | TIMESTAMP | |
| `ends_at` | TIMESTAMP | |
| `created_at` | TIMESTAMP | |

#### `Room`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `round_id` | UUID FK → Round | |
| `venue_id` | UUID FK → Venue | Nullable |
| `room_number` | INT | Display order |

#### `DrawSeat`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `room_id` | UUID FK → Room | |
| `position` | ENUM | `OG`, `OO`, `CG`, `CO` |
| `team_id` | UUID FK → Team | |
| **Unique** | `(room_id, position)` | |

#### `Allocation`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `round_id` | UUID FK → Round | |
| `room_id` | UUID FK → Room | |
| `judge_id` | UUID FK → Judge | |
| `role` | ENUM | `chair`, `panel`, `trainee` |
| **Unique** | `(room_id, judge_id)` | |

#### `Ballot`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `round_id` | UUID FK → Round | |
| `room_id` | UUID FK → Room | |
| `status` | ENUM | `missing`, `pending`, `done` |
| `submitted_by` | UUID FK → User | |
| `submitted_at` | TIMESTAMP | |
| `scores` | JSONB | `{OG: {team: N, speakers: [N,N]}, ...}` |
| `ranking` | JSONB | `{OG: 1, OO: 3, CG: 2, CO: 4}` |
| `notes` | TEXT | |
| `locked` | BOOLEAN | Prevent further edits |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

#### `StandingSnapshot`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `tournament_id` | UUID FK → Tournament | |
| `computed_at` | TIMESTAMP | |
| `round_id` | UUID FK → Round | Up to which round |
| `payload` | JSONB | Full standings data |

#### `BreakCategory`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `tournament_id` | UUID FK → Tournament | |
| `name` | VARCHAR(100) | e.g. "Open", "ESL", "EFL" |
| `slug` | VARCHAR(50) | URL-safe |
| `break_size` | INT | Number of teams that break |
| `is_general` | BOOLEAN | Main break category |
| `published` | BOOLEAN | |

#### `BreakTeam`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `category_id` | UUID FK → BreakCategory | |
| `team_id` | UUID FK → Team | |
| `rank` | INT | Position in break |

#### `Notification`
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `user_id` | UUID FK → User | |
| `tournament_id` | UUID FK → Tournament | Nullable |
| `type` | VARCHAR(50) | e.g. `ballot_submitted`, `draw_released` |
| `title` | VARCHAR(255) | |
| `body` | TEXT | |
| `read` | BOOLEAN | Default false |
| `created_at` | TIMESTAMP | |

---

## 5. RBAC Permissions

| Action | admin | tabber | runner | viewer |
|--------|:-----:|:------:|:------:|:------:|
| View tournament | ✅ | ✅ | ✅ | ✅ |
| Edit tournament settings | ✅ | ❌ | ❌ | ❌ |
| Delete tournament | ✅ | ❌ | ❌ | ❌ |
| CRUD teams/judges/venues | ✅ | ✅ | ❌ | ❌ |
| Create/manage rounds | ✅ | ✅ | ❌ | ❌ |
| Generate/publish draw | ✅ | ✅ | ❌ | ❌ |
| Auto-allocate judges | ✅ | ✅ | ❌ | ❌ |
| Manual allocation edits | ✅ | ✅ | ❌ | ❌ |
| Submit ballot | ✅ | ✅ | ✅ | ❌ |
| Lock/unlock ballot | ✅ | ✅ | ❌ | ❌ |
| Export ballots | ✅ | ✅ | ❌ | ❌ |
| View standings | ✅ | ✅ | ✅ | ✅ |
| Recompute standings | ✅ | ✅ | ❌ | ❌ |
| Compute/publish breaks | ✅ | ❌ | ❌ | ❌ |
| Check-in teams/judges/venues | ✅ | ✅ | ✅ | ❌ |
| View draw | ✅ | ✅ | ✅ | ✅ |
| View notifications | ✅ | ✅ | ✅ | ✅ |
| Motion analysis | ✅ | ✅ | ❌ | ❌ |

---

## 6. API Endpoint Reference

**Base path:** `/api/v1`
**Auth:** Session-based (Django session cookie) for this Django app. JWT alternative documented where applicable.
**Content-Type:** `application/json`

---

### 6.1 Auth & Users

#### `POST /api/v1/auth/login`
- **Auth:** No
- **Body:**
```json
{ "email": "admin@example.com", "password": "secret123" }
```
- **Response 200:**
```json
{
  "user": { "id": "uuid", "name": "Alice", "email": "admin@example.com", "is_superuser": true },
  "session_id": "abc123",
  "expires_at": "2026-03-02T00:00:00Z"
}
```
- **Error 401:**
```json
{ "error": "invalid_credentials", "message": "Invalid email or password." }
```

#### `POST /api/v1/auth/logout`
- **Auth:** Yes
- **Body:** None
- **Response 200:**
```json
{ "message": "Logged out." }
```

#### `GET /api/v1/auth/me`
- **Auth:** Yes
- **Response 200:**
```json
{
  "id": "uuid",
  "name": "Alice",
  "email": "admin@example.com",
  "is_superuser": true,
  "tournaments": [
    { "id": "uuid", "name": "Worlds 2026", "role": "admin" }
  ]
}
```

#### `POST /api/v1/auth/refresh` *(JWT mode only)*
- **Auth:** Yes (refresh token in cookie)
- **Response 200:**
```json
{ "access_token": "eyJ...", "expires_in": 3600 }
```

#### `GET /api/v1/users/:userId`
- **Auth:** Yes
- **Roles:** admin
- **Response 200:**
```json
{
  "id": "uuid", "name": "Alice", "email": "admin@example.com",
  "is_superuser": true, "created_at": "2026-01-01T00:00:00Z"
}
```

#### `PATCH /api/v1/users/:userId`
- **Auth:** Yes
- **Roles:** admin
- **Body:**
```json
{ "name": "Alice B.", "email": "newalice@example.com" }
```
- **Response 200:** Updated user object (same schema as GET).

---

### 6.2 Tournaments

#### `GET /api/v1/tournaments`
- **Auth:** Yes
- **Roles:** any authenticated
- **Query Params:** `?page=1&per_page=20&search=worlds`
- **Response 200:**
```json
{
  "items": [
    {
      "id": "uuid", "name": "Worlds 2026", "short_name": "Worlds",
      "slug": "worlds-2026", "format": "bp", "total_rounds": 9,
      "active": true, "role": "admin",
      "created_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total": 1, "page": 1, "per_page": 20
}
```

#### `POST /api/v1/tournaments`
- **Auth:** Yes
- **Roles:** admin
- **Body:**
```json
{
  "name": "Worlds 2026",
  "short_name": "Worlds",
  "format": "bp",
  "timezone": "Asia/Tokyo",
  "total_rounds": 9
}
```
- **Response 201:** Full tournament object.

#### `GET /api/v1/tournaments/:tournamentId`
- **Auth:** Yes
- **Roles:** any with membership
- **Response 200:**
```json
{
  "id": "uuid", "name": "Worlds 2026", "short_name": "Worlds",
  "slug": "worlds-2026", "format": "bp", "timezone": "Asia/Tokyo",
  "total_rounds": 9, "active": true,
  "current_round": { "id": "uuid", "seq": 3, "name": "Round 3", "abbreviation": "R3", "status": "active" },
  "team_count": 48, "judge_count": 30, "venue_count": 12,
  "created_at": "2026-01-01T00:00:00Z"
}
```

#### `PATCH /api/v1/tournaments/:tournamentId`
- **Auth:** Yes
- **Roles:** admin
- **Body:** Any subset of tournament fields.
- **Response 200:** Updated tournament object.

#### `DELETE /api/v1/tournaments/:tournamentId`
- **Auth:** Yes
- **Roles:** admin
- **Response 204:** No content.

---

### 6.3 Dashboard / Overview

#### `GET /api/v1/tournaments/:tournamentId/overview`
- **Auth:** Yes
- **Roles:** admin, tabber, runner, viewer
- **Description:** Single aggregated endpoint returning everything needed to render the Overview page.
- **Response 200:**
```json
{
  "tournamentContext": {
    "id": "uuid",
    "name": "Worlds 2026",
    "short_name": "Worlds",
    "format": "bp",
    "total_rounds": 9,
    "current_round_number": 3,
    "current_round_status": "active"
  },
  "stats": {
    "teams": { "count": 48, "institutions": 24 },
    "judges": { "count": 30, "checked_in": 28 },
    "rounds": { "total": 9, "completed": 2 },
    "current": { "label": "R3", "status": "active" }
  },
  "roundTracker": [
    { "seq": 1, "abbreviation": "R1", "name": "Round 1", "status": "completed" },
    { "seq": 2, "abbreviation": "R2", "name": "Round 2", "status": "completed" },
    { "seq": 3, "abbreviation": "R3", "name": "Round 3", "status": "active" },
    { "seq": 4, "abbreviation": "R4", "name": "Round 4", "status": "pending" },
    { "seq": 5, "abbreviation": "R5", "name": "Round 5", "status": "pending" }
  ],
  "currentRound": {
    "id": "uuid",
    "seq": 3,
    "name": "Round 3",
    "abbreviation": "R3",
    "status": "active",
    "draw_status": "released",
    "starts_at": "2026-03-01T09:00:00Z"
  },
  "currentMotion": {
    "text": "This House believes that developing nations should prioritize industrialization over environmental protection.",
    "info_slide": null
  },
  "currentDrawRooms": [
    {
      "room_id": "uuid",
      "room_number": 1,
      "venue_name": "Hall A",
      "og": { "team_id": "uuid", "name": "Oxford A", "institution": "Oxford" },
      "oo": { "team_id": "uuid", "name": "Cambridge B", "institution": "Cambridge" },
      "cg": { "team_id": "uuid", "name": "Yale A", "institution": "Yale" },
      "co": { "team_id": "uuid", "name": "Harvard C", "institution": "Harvard" },
      "chair": { "judge_id": "uuid", "name": "Dr. Smith" },
      "panels": [{ "judge_id": "uuid", "name": "J. Doe" }],
      "ballot_status": "done"
    },
    {
      "room_id": "uuid",
      "room_number": 2,
      "venue_name": "Hall B",
      "og": { "team_id": "uuid", "name": "NUS A", "institution": "NUS" },
      "oo": { "team_id": "uuid", "name": "LSE A", "institution": "LSE" },
      "cg": { "team_id": "uuid", "name": "Princeton A", "institution": "Princeton" },
      "co": { "team_id": "uuid", "name": "UQ A", "institution": "UQ" },
      "chair": { "judge_id": "uuid", "name": "Prof. Lee" },
      "panels": [],
      "ballot_status": "pending"
    }
  ],
  "ballotSummary": {
    "submitted": 8,
    "pending": 3,
    "missing": 1,
    "total": 12,
    "percent": 67
  },
  "checkinSummary": {
    "teams": { "checked_in": 46, "total": 48 },
    "judges": { "checked_in": 28, "total": 30 },
    "venues": { "checked_in": 12, "total": 12 }
  },
  "quickActions": [
    {
      "key": "generate_draw",
      "title": "Generate Draw",
      "subtitle": "Create pairings for current round",
      "icon": "dice",
      "color": "violet",
      "enabled": false,
      "disabled_reason": "Draw already generated for this round."
    },
    {
      "key": "allocate_judges",
      "title": "Allocate Judges",
      "subtitle": "Auto-assign adjudicators",
      "icon": "scales",
      "color": "amber",
      "enabled": true,
      "disabled_reason": null
    },
    {
      "key": "enter_ballots",
      "title": "Enter Ballots",
      "subtitle": "Submit or review ballots",
      "icon": "pencil",
      "color": "green",
      "enabled": true,
      "disabled_reason": null
    },
    {
      "key": "advance_round",
      "title": "Advance Round",
      "subtitle": "Close current, open next",
      "icon": "forward",
      "color": "red",
      "enabled": false,
      "disabled_reason": "Not all ballots submitted. 4 remaining."
    }
  ]
}
```

---

### 6.4 Rounds

#### `GET /api/v1/tournaments/:tournamentId/rounds`
- **Auth:** Yes
- **Roles:** any
- **Response 200:**
```json
{
  "items": [
    {
      "id": "uuid", "seq": 1, "name": "Round 1", "abbreviation": "R1",
      "status": "completed", "draw_status": "released",
      "motion_text": "THBT social media...", "starts_at": "2026-03-01T09:00:00Z"
    }
  ]
}
```

#### `POST /api/v1/tournaments/:tournamentId/rounds`
- **Auth:** Yes
- **Roles:** admin
- **Body:**
```json
{
  "name": "Round 6",
  "abbreviation": "R6",
  "motion_text": "This House would...",
  "starts_at": "2026-03-01T14:00:00Z"
}
```
- **Response 201:** Full round object.

#### `GET /api/v1/tournaments/:tournamentId/rounds/:roundId`
- **Auth:** Yes
- **Roles:** any
- **Response 200:** Single round object (same fields as list item + `ends_at`, `info_slide`).

#### `PATCH /api/v1/tournaments/:tournamentId/rounds/:roundId`
- **Auth:** Yes
- **Roles:** admin
- **Body:** Any subset: `status`, `motion_text`, `info_slide`, `starts_at`, `ends_at`.
- **Response 200:** Updated round object.

#### `POST /api/v1/tournaments/:tournamentId/rounds/:roundId/activate`
- **Auth:** Yes
- **Roles:** admin
- **Body:** None
- **Response 200:**
```json
{ "id": "uuid", "status": "active", "message": "Round activated." }
```

#### `POST /api/v1/tournaments/:tournamentId/rounds/:roundId/close`
- **Auth:** Yes
- **Roles:** admin
- **Body:** None
- **Response 200:**
```json
{ "id": "uuid", "status": "completed", "message": "Round closed." }
```

---

### 6.5 Draws

#### `GET /api/v1/tournaments/:tournamentId/rounds/:roundId/draw`
- **Auth:** Yes
- **Roles:** any
- **Response 200:**
```json
{
  "round_id": "uuid",
  "draw_status": "released",
  "rooms": [
    {
      "room_id": "uuid",
      "room_number": 1,
      "venue": { "id": "uuid", "name": "Hall A" },
      "seats": {
        "OG": { "team_id": "uuid", "name": "Oxford A", "institution": "Oxford" },
        "OO": { "team_id": "uuid", "name": "Cambridge B", "institution": "Cambridge" },
        "CG": { "team_id": "uuid", "name": "Yale A", "institution": "Yale" },
        "CO": { "team_id": "uuid", "name": "Harvard C", "institution": "Harvard" }
      },
      "judges": [
        { "judge_id": "uuid", "name": "Dr. Smith", "role": "chair" },
        { "judge_id": "uuid", "name": "J. Doe", "role": "panel" }
      ],
      "ballot_status": "done"
    }
  ]
}
```

#### `POST /api/v1/tournaments/:tournamentId/rounds/:roundId/draw/generate`
- **Auth:** Yes
- **Roles:** admin
- **Body:**
```json
{ "algorithm": "power_paired", "avoid_institution": true, "avoid_history": true }
```
- **Response 201:**
```json
{ "round_id": "uuid", "rooms_created": 12, "draw_status": "draft", "message": "Draw generated." }
```

#### `POST /api/v1/tournaments/:tournamentId/rounds/:roundId/draw/publish`
- **Auth:** Yes
- **Roles:** admin
- **Body:** None
- **Response 200:**
```json
{ "draw_status": "released", "message": "Draw published." }
```

#### `POST /api/v1/tournaments/:tournamentId/rounds/:roundId/draw/unpublish`
- **Auth:** Yes
- **Roles:** admin
- **Body:** None
- **Response 200:**
```json
{ "draw_status": "confirmed", "message": "Draw unpublished." }
```

#### `PATCH /api/v1/tournaments/:tournamentId/rounds/:roundId/draw/rooms/:roomId`
- **Auth:** Yes
- **Roles:** admin
- **Body:**
```json
{
  "venue_id": "uuid",
  "seats": {
    "OG": "team-uuid-1",
    "OO": "team-uuid-2",
    "CG": "team-uuid-3",
    "CO": "team-uuid-4"
  }
}
```
- **Response 200:** Updated room object.

---

### 6.6 Ballots

#### `GET /api/v1/tournaments/:tournamentId/rounds/:roundId/ballots`
- **Auth:** Yes
- **Roles:** admin, tabber, runner
- **Query Params:** `?status=pending&page=1&per_page=50`
- **Response 200:**
```json
{
  "items": [
    {
      "id": "uuid", "room_id": "uuid", "room_number": 1,
      "venue_name": "Hall A", "status": "done",
      "submitted_by": { "id": "uuid", "name": "Dr. Smith" },
      "submitted_at": "2026-03-01T10:30:00Z",
      "locked": false
    }
  ],
  "summary": { "done": 8, "pending": 3, "missing": 1, "total": 12 }
}
```

#### `POST /api/v1/tournaments/:tournamentId/rounds/:roundId/ballots`
- **Auth:** Yes
- **Roles:** admin, tabber, runner
- **Body:**
```json
{
  "room_id": "uuid",
  "ranking": { "OG": 1, "OO": 3, "CG": 2, "CO": 4 },
  "scores": {
    "OG": { "team": 270, "speakers": [135, 135] },
    "OO": { "team": 255, "speakers": [128, 127] },
    "CG": { "team": 262, "speakers": [131, 131] },
    "CO": { "team": 248, "speakers": [124, 124] }
  },
  "notes": "Close call between OG and CG."
}
```
- **Response 201:**
```json
{
  "id": "uuid", "room_id": "uuid", "status": "done",
  "submitted_by": { "id": "uuid", "name": "Alice" },
  "submitted_at": "2026-03-01T10:30:00Z",
  "locked": false
}
```

#### `GET /api/v1/tournaments/:tournamentId/rounds/:roundId/ballots/:ballotId`
- **Auth:** Yes
- **Roles:** admin, tabber
- **Response 200:** Full ballot with scores, ranking, notes.

#### `PATCH /api/v1/tournaments/:tournamentId/rounds/:roundId/ballots/:ballotId`
- **Auth:** Yes
- **Roles:** admin, tabber
- **Precondition:** `locked == false`
- **Body:** Same as POST body (partial updates allowed).
- **Response 200:** Updated ballot.
- **Error 409:**
```json
{ "error": "ballot_locked", "message": "Ballot is locked. Unlock first." }
```

#### `POST /api/v1/tournaments/:tournamentId/rounds/:roundId/ballots/:ballotId/lock`
- **Auth:** Yes
- **Roles:** admin
- **Body:** None
- **Response 200:**
```json
{ "id": "uuid", "locked": true, "message": "Ballot locked." }
```

#### `POST /api/v1/tournaments/:tournamentId/rounds/:roundId/ballots/:ballotId/unlock`
- **Auth:** Yes
- **Roles:** admin
- **Body:** None
- **Response 200:**
```json
{ "id": "uuid", "locked": false, "message": "Ballot unlocked." }
```

#### `POST /api/v1/tournaments/:tournamentId/rounds/:roundId/ballots/export`
- **Auth:** Yes
- **Roles:** admin
- **Query Params:** `?format=csv|json|pdf`
- **Response 200:** File download or JSON blob of all ballots for the round.

---

### 6.7 Allocations

#### `GET /api/v1/tournaments/:tournamentId/rounds/:roundId/allocations`
- **Auth:** Yes
- **Roles:** admin, tabber
- **Response 200:**
```json
{
  "items": [
    {
      "id": "uuid", "room_id": "uuid", "room_number": 1,
      "judge": { "id": "uuid", "name": "Dr. Smith", "institution": "Oxford", "rank": 85 },
      "role": "chair"
    },
    {
      "id": "uuid", "room_id": "uuid", "room_number": 1,
      "judge": { "id": "uuid", "name": "J. Doe", "institution": "LSE", "rank": 70 },
      "role": "panel"
    }
  ]
}
```

#### `POST /api/v1/tournaments/:tournamentId/rounds/:roundId/allocations/auto`
- **Auth:** Yes
- **Roles:** admin
- **Body:**
```json
{ "algorithm": "hungarian", "min_panel_size": 1, "max_panel_size": 3 }
```
- **Response 201:**
```json
{ "allocations_created": 24, "unallocated_judges": 2, "message": "Auto-allocation complete." }
```

#### `PATCH /api/v1/tournaments/:tournamentId/rounds/:roundId/allocations/:allocId`
- **Auth:** Yes
- **Roles:** admin
- **Body:**
```json
{ "room_id": "new-room-uuid", "role": "panel" }
```
- **Response 200:** Updated allocation object.

---

### 6.8 Teams (Setup)

#### `GET /api/v1/tournaments/:tournamentId/teams`
- **Auth:** Yes
- **Roles:** any
- **Query Params:** `?search=oxford&institution=Oxford&page=1&per_page=50&active=true`
- **Response 200:**
```json
{
  "items": [
    {
      "id": "uuid", "name": "Oxford A", "short_name": "Ox A",
      "institution": "Oxford", "speakers": [{"name":"J. Mill"},{"name":"A. Lock"}],
      "checked_in": true, "active": true
    }
  ],
  "total": 48, "page": 1, "per_page": 50
}
```

#### `POST /api/v1/tournaments/:tournamentId/teams`
- **Auth:** Yes
- **Roles:** admin
- **Body:**
```json
{
  "name": "Oxford A", "short_name": "Ox A", "institution": "Oxford",
  "speakers": [{"name": "J. Mill", "email": "jm@ox.ac.uk"}, {"name": "A. Lock"}]
}
```
- **Response 201:** Full team object.

#### `GET /api/v1/tournaments/:tournamentId/teams/:teamId`
- **Auth:** Yes
- **Roles:** any
- **Response 200:** Full team object (same fields as list item).

#### `PATCH /api/v1/tournaments/:tournamentId/teams/:teamId`
- **Auth:** Yes
- **Roles:** admin
- **Body:** Any subset of team fields.
- **Response 200:** Updated team object.

#### `DELETE /api/v1/tournaments/:tournamentId/teams/:teamId`
- **Auth:** Yes
- **Roles:** admin
- **Response 204:** No content.

---

### 6.9 Judges (Setup)

#### `GET /api/v1/tournaments/:tournamentId/judges`
- **Auth:** Yes
- **Roles:** any
- **Query Params:** `?search=smith&checked_in=true&page=1&per_page=50`
- **Response 200:**
```json
{
  "items": [
    {
      "id": "uuid", "name": "Dr. Smith", "institution": "Oxford",
      "email": "smith@ox.ac.uk", "checked_in": true, "rank": 85,
      "is_independent": false, "active": true
    }
  ],
  "total": 30, "page": 1, "per_page": 50
}
```

#### `POST /api/v1/tournaments/:tournamentId/judges`
- **Auth:** Yes
- **Roles:** admin
- **Body:**
```json
{
  "name": "Dr. Smith", "institution": "Oxford",
  "email": "smith@ox.ac.uk", "rank": 85, "is_independent": false
}
```
- **Response 201:** Full judge object.

#### `GET /api/v1/tournaments/:tournamentId/judges/:judgeId`
- **Auth:** Yes
- **Roles:** any
- **Response 200:** Full judge object.

#### `PATCH /api/v1/tournaments/:tournamentId/judges/:judgeId`
- **Auth:** Yes
- **Roles:** admin
- **Body:** Any subset.
- **Response 200:** Updated judge object.

#### `POST /api/v1/tournaments/:tournamentId/judges/:judgeId/checkin`
- **Auth:** Yes
- **Roles:** admin, runner
- **Body:** None
- **Response 200:**
```json
{ "id": "uuid", "checked_in": true, "message": "Judge checked in." }
```

#### `POST /api/v1/tournaments/:tournamentId/judges/:judgeId/checkout`
- **Auth:** Yes
- **Roles:** admin, runner
- **Body:** None
- **Response 200:**
```json
{ "id": "uuid", "checked_in": false, "message": "Judge checked out." }
```

---

### 6.10 Venues (Setup)

#### `GET /api/v1/tournaments/:tournamentId/venues`
- **Auth:** Yes
- **Roles:** any
- **Query Params:** `?search=hall&checked_in=true&page=1&per_page=50`
- **Response 200:**
```json
{
  "items": [
    {
      "id": "uuid", "name": "Hall A", "capacity": 50,
      "checked_in": true, "priority": 10, "active": true
    }
  ],
  "total": 12, "page": 1, "per_page": 50
}
```

#### `POST /api/v1/tournaments/:tournamentId/venues`
- **Auth:** Yes
- **Roles:** admin
- **Body:**
```json
{ "name": "Hall A", "capacity": 50, "priority": 10 }
```
- **Response 201:** Full venue object.

#### `GET /api/v1/tournaments/:tournamentId/venues/:venueId`
- **Auth:** Yes
- **Roles:** any
- **Response 200:** Full venue object.

#### `PATCH /api/v1/tournaments/:tournamentId/venues/:venueId`
- **Auth:** Yes
- **Roles:** admin
- **Body:** Any subset.
- **Response 200:** Updated venue object.

#### `DELETE /api/v1/tournaments/:tournamentId/venues/:venueId`
- **Auth:** Yes
- **Roles:** admin
- **Response 204:** No content.

#### `POST /api/v1/tournaments/:tournamentId/venues/:venueId/checkin`
- **Auth:** Yes
- **Roles:** admin, runner
- **Body:** None
- **Response 200:**
```json
{ "id": "uuid", "checked_in": true, "message": "Venue checked in." }
```

#### `POST /api/v1/tournaments/:tournamentId/venues/:venueId/checkout`
- **Auth:** Yes
- **Roles:** admin, runner
- **Body:** None
- **Response 200:**
```json
{ "id": "uuid", "checked_in": false, "message": "Venue checked out." }
```

---

### 6.11 Standings & Results

#### `GET /api/v1/tournaments/:tournamentId/standings`
- **Auth:** Yes
- **Roles:** any
- **Query Params:** `?as_of_round=3`
- **Response 200:**
```json
{
  "computed_at": "2026-03-01T10:00:00Z",
  "as_of_round": 3,
  "teams": [
    {
      "rank": 1, "team_id": "uuid", "name": "Oxford A", "institution": "Oxford",
      "wins": 3, "points": 9, "speaker_score": 810.0,
      "margin": 45.0, "rounds": [
        { "round": 1, "position": "OG", "rank": 1, "points": 3, "speaker_score": 270 },
        { "round": 2, "position": "CO", "rank": 2, "points": 2, "speaker_score": 265 },
        { "round": 3, "position": "CG", "rank": 1, "points": 3, "speaker_score": 275 }
      ]
    }
  ]
}
```

#### `GET /api/v1/tournaments/:tournamentId/results`
- **Auth:** Yes
- **Roles:** any
- **Response 200:**
```json
{
  "rounds": [
    {
      "round_id": "uuid", "seq": 1, "name": "Round 1",
      "motion": "THBT social media...",
      "rooms": [
        {
          "room_number": 1, "venue": "Hall A",
          "result": { "OG": 1, "OO": 3, "CG": 2, "CO": 4 },
          "teams": {
            "OG": { "name": "Oxford A", "score": 270 },
            "OO": { "name": "Cambridge B", "score": 255 },
            "CG": { "name": "Yale A", "score": 262 },
            "CO": { "name": "Harvard C", "score": 248 }
          }
        }
      ]
    }
  ]
}
```

#### `POST /api/v1/tournaments/:tournamentId/recompute`
- **Auth:** Yes
- **Roles:** admin
- **Body:** None
- **Response 200:**
```json
{
  "message": "Standings recomputed.",
  "snapshot_id": "uuid",
  "computed_at": "2026-03-01T10:05:00Z"
}
```

---

### 6.12 Breaks

#### `GET /api/v1/tournaments/:tournamentId/breaks`
- **Auth:** Yes
- **Roles:** any
- **Response 200:**
```json
{
  "categories": [
    {
      "id": "uuid", "name": "Open", "slug": "open", "break_size": 16,
      "is_general": true, "published": false,
      "teams": [
        { "rank": 1, "team_id": "uuid", "name": "Oxford A", "institution": "Oxford", "points": 21 }
      ]
    }
  ]
}
```

#### `POST /api/v1/tournaments/:tournamentId/breaks/compute`
- **Auth:** Yes
- **Roles:** admin
- **Body:**
```json
{ "category_id": "uuid" }
```
- **Response 200:**
```json
{ "category_id": "uuid", "teams_breaking": 16, "message": "Break computed." }
```

#### `PATCH /api/v1/tournaments/:tournamentId/breaks/publish`
- **Auth:** Yes
- **Roles:** admin
- **Body:**
```json
{ "category_id": "uuid", "published": true }
```
- **Response 200:**
```json
{ "category_id": "uuid", "published": true, "message": "Break published." }
```

---

### 6.13 Motion Analysis

#### `POST /api/v1/tournaments/:tournamentId/rounds/:roundId/motion/analyze`
- **Auth:** Yes
- **Roles:** admin, tabber
- **Body:**
```json
{ "text": "This House believes that developing nations should prioritize industrialization over environmental protection." }
```
- **Response 200:**
```json
{
  "summary": "A motion about the trade-off between economic development and environmental sustainability in developing countries.",
  "themes": ["economic development", "environmental policy", "global inequality", "industrialization"],
  "stakeholders": ["developing nations", "local populations", "global community", "future generations", "corporations"],
  "clashes": [
    "Short-term economic growth vs. long-term environmental sustainability",
    "National sovereignty vs. global responsibility",
    "Poverty alleviation vs. climate change mitigation"
  ],
  "definitions": [
    { "term": "developing nations", "suggested": "Countries with lower GDP per capita and industrialization levels, typically classified by the UN/World Bank." },
    { "term": "prioritize", "suggested": "Allocate more resources/policy focus to, not exclusively pursue at the expense of." },
    { "term": "industrialization", "suggested": "The process of building manufacturing and heavy industry infrastructure." }
  ],
  "biasWarnings": [
    "Motion may favour Proposition as it maps to a common development economics narrative.",
    "Consider whether the binary framing is fair — most real policy is about balance."
  ]
}
```

---

### 6.14 Notifications

#### `GET /api/v1/notifications`
- **Auth:** Yes
- **Roles:** any
- **Query Params:** `?unread_only=true&page=1&per_page=20`
- **Response 200:**
```json
{
  "items": [
    {
      "id": "uuid", "type": "ballot_submitted",
      "title": "Ballot submitted for Room 3",
      "body": "Dr. Smith submitted the ballot for Hall C, Round 3.",
      "tournament_id": "uuid", "read": false,
      "created_at": "2026-03-01T10:30:00Z"
    }
  ],
  "unread_count": 3, "total": 15
}
```

#### `POST /api/v1/notifications/mark-read`
- **Auth:** Yes
- **Roles:** any
- **Body:**
```json
{ "notification_ids": ["uuid1", "uuid2"] }
```
- **Response 200:**
```json
{ "marked": 2 }
```

---

## 7. Overview Page State Flow

### Load Sequence

```
1. User navigates to /tournaments/:id/overview
2. Auth check → redirect to /login if unauthenticated
3. RBAC check → verify user has membership in tournament
4. GET /api/v1/tournaments/:tournamentId/overview
     ├── Server aggregates from:
     │   ├── Tournament model (context + stats)
     │   ├── Round.objects.filter(tournament=t).order_by('seq')
     │   ├── DrawSeat + Room + Ballot for current round
     │   ├── Allocation for current round
     │   └── Check-in counts from Team/Judge/Venue
     └── Returns single JSON response
5. Render components:
     a. PageHeader ← tournamentContext
     b. StatsRow ← stats
     c. DrawPanel:
        i.  RoundTracker ← roundTracker[]
        ii. MotionStrip ← currentMotion
        iii. DrawTable ← currentDrawRooms[]
        iv. DrawFooter ← ballotSummary
     d. CompletionRing ← ballotSummary
     e. QuickActions ← quickActions[] (with enabled/disabled)
     f. CheckInWidget ← checkinSummary
```

### Quick Actions Enable/Disable Rules

| Action | Enabled When | Disabled Reason |
|--------|-------------|-----------------|
| Generate Draw | `currentRound.draw_status == 'none'` | "Draw already generated for this round." |
| Allocate Judges | `currentRound.draw_status in ['draft','confirmed','released']` | "Generate draw first." |
| Enter Ballots | `currentRound.draw_status == 'released'` | "Draw not yet released." |
| Advance Round | `ballotSummary.submitted == ballotSummary.total && ballotSummary.total > 0` | "Not all ballots submitted. N remaining." |

### Realtime Updates (Optional)

```
6. If WebSocket enabled:
   Connect to WS /api/v1/tournaments/:id/rounds/:currentRoundId/live
   On `ballot_submitted`:
     → Update DrawTable row status chip
     → Update CompletionRing values
     → Update DrawFooter progress
     → Update QuickActions (check if advance_round should enable)
   On `checkin_updated`:
     → Update CheckInWidget counts
   On `draw_updated`:
     → Refetch full draw data
```

---

## 8. Realtime WebSocket Events

### Connection

```
WS /api/v1/tournaments/:tournamentId/rounds/:roundId/live
Headers: { Authorization: "Session <session_id>" }
```

### Event Schemas

#### `ballot_submitted`
```json
{
  "event": "ballot_submitted",
  "data": {
    "room_id": "uuid",
    "ballot_id": "uuid",
    "status": "done",
    "submitted_by": "Dr. Smith",
    "submitted_at": "2026-03-01T10:30:00Z",
    "summary": { "submitted": 9, "pending": 2, "missing": 1, "total": 12, "percent": 75 }
  }
}
```

#### `draw_updated`
```json
{
  "event": "draw_updated",
  "data": {
    "round_id": "uuid",
    "draw_status": "released",
    "rooms_count": 12
  }
}
```

#### `allocation_updated`
```json
{
  "event": "allocation_updated",
  "data": {
    "round_id": "uuid",
    "allocations_count": 24
  }
}
```

#### `checkin_updated`
```json
{
  "event": "checkin_updated",
  "data": {
    "entity_type": "judge",
    "entity_id": "uuid",
    "entity_name": "Dr. Smith",
    "checked_in": true,
    "summary": { "checked_in": 29, "total": 30 }
  }
}
```

---

## 9. Error Handling Patterns

### HTTP Error Response Schema

All errors follow this structure:

```json
{
  "error": "error_code",
  "message": "Human-readable description.",
  "details": {}
}
```

### Error Codes

| HTTP | Code | When |
|------|------|------|
| 400 | `validation_error` | Invalid request body. `details` contains field-level errors. |
| 401 | `unauthenticated` | Missing or expired session/token. |
| 403 | `forbidden` | User lacks permission for this action. |
| 404 | `not_found` | Resource does not exist. |
| 409 | `conflict` | State conflict (e.g., ballot locked, draw already generated). |
| 422 | `unprocessable` | Semantic error (e.g., cannot close round with missing ballots). |
| 429 | `rate_limited` | Too many requests. |
| 500 | `internal_error` | Unexpected server error. |

### Validation Error Example

```json
{
  "error": "validation_error",
  "message": "Request body contains invalid fields.",
  "details": {
    "name": ["This field is required."],
    "email": ["Enter a valid email address."],
    "rank": ["Ensure this value is between 0 and 100."]
  }
}
```

### Conflict Error Example

```json
{
  "error": "conflict",
  "message": "Cannot generate draw: draw already exists for Round 3.",
  "details": {
    "current_draw_status": "draft",
    "suggestion": "Delete the existing draw first, or publish it."
  }
}
```

---

## 10. Auth Strategy

### Chosen: Session-Based Authentication (Django Sessions)

This is consistent with the existing Django/Tabbycat stack.

| Aspect | Detail |
|--------|--------|
| **Login** | `POST /api/v1/auth/login` with email+password → creates Django session → returns `Set-Cookie: sessionid=...` |
| **Session storage** | Django default (database-backed, or Redis via `django-redis`) |
| **CSRF** | Django CSRF middleware active. Frontend reads `csrftoken` cookie and sends `X-CSRFToken` header. |
| **Session lifetime** | 24 hours, sliding window (reset on each request). |
| **Logout** | `POST /api/v1/auth/logout` → destroys session. |
| **RBAC enforcement** | Custom Django middleware checks `TournamentMembership.role` against endpoint permission map. |
| **Public endpoints** | Public tournament view (`/t/:slug`) does not require auth. Served by Django template views. |

### Permission Middleware (Pseudo-code)

```python
class TournamentRBACMiddleware:
    PERMISSION_MAP = {
        'tournament-delete':   ['admin'],
        'draw-generate':       ['admin', 'tabber'],
        'ballot-submit':       ['admin', 'tabber', 'runner'],
        'checkin-toggle':      ['admin', 'tabber', 'runner'],
        'standings-view':      ['admin', 'tabber', 'runner', 'viewer'],
    }

    def check_permission(self, user, tournament_id, action):
        membership = TournamentMembership.objects.get(
            user=user, tournament_id=tournament_id
        )
        allowed_roles = self.PERMISSION_MAP.get(action, [])
        if membership.role not in allowed_roles:
            raise PermissionDenied()
```

---

## Files Produced

| File | Purpose |
|------|---------|
| `public_tournament_index.html` | Updated: IBM Plex Mono typography, public view layout |
| `tournament_director_dashboard.html` | New: Tab director dashboard with full admin layout |
| `ARCHITECTURE.md` | This file: complete app architecture specification |
