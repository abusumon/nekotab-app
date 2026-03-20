# nekocongress Pre-Deploy Audit Report

**Date:** Phase 3 Complete  
**Scope:** All nekocongress files (FastAPI microservice + Django wiring + Vue components + Nginx + Docker)

---

## Issues Found & Fixed

### CRITICAL (would prevent the feature from working)

| # | Issue | Files | Status |
|---|-------|-------|--------|
| C01 | `congress_events` missing from `INSTALLED_APPS` — Django can't discover templates/URLs | `settings/core.py`, new `congress_events/apps.py` | ✅ Fixed |
| C02 | Congress URL routes not wired into Django `tournaments/urls.py` | `tournaments/urls.py` | ✅ Fixed |
| C03 | Nginx (Heroku ERB) missing `upstream nekocongress` and `/api/congress/` proxy | `config/nginx.conf.erb` | ✅ Fixed |
| C04 | Nginx (Docker) missing `upstream nekocongress` and `/api/congress/` proxy | `config/nginx-docker.conf` | ✅ Fixed |
| C05 | `docker-compose.yml` missing `nekocongress` service + nginx dependency | `docker-compose.yml`, new `nekocongress/Dockerfile` | ✅ Fixed |
| C06 | `floor.py` change-legislation uses invalid docket_status enums (`DEBATED`/`ACTIVE` → `CARRIED_OVER`/`DEBATING`) | `nekocongress/routers/floor.py` | ✅ Fixed |
| C07 | `chamberId` undefined in 4 session Vue components — WebSocket can't connect | `LiveSessionFloor.vue`, `ScorerBallot.vue`, `StudentSessionView.vue`, `ParliamentarianPanel.vue` | ✅ Fixed (fetch from session API) |
| C08 | 7 API path mismatches in LiveSessionFloor.vue (wrong endpoint paths for recognize, end-speech, questions, speeches, vote) | `LiveSessionFloor.vue` | ✅ Fixed |
| C08b | API path mismatches in ScorerBallot, StudentSessionView, ParliamentarianPanel (`/floor/session/{id}/speeches/` → `/floor/speeches/{id}/`) | `ScorerBallot.vue`, `StudentSessionView.vue`, `ParliamentarianPanel.vue` | ✅ Fixed |
| C08c | ScorerBallot score POST path `/scores/` → `/scores/speech/` | `ScorerBallot.vue` | ✅ Fixed |
| C09 | `ScorerBallot.loadScores` iterated `data` as array but `SessionScoresResponse` is an object `{session_id, speech_scores, rankings, po_scores}`. Also `SpeechScoreResponse` lacks `legislator_id` — need cross-ref with speeches | `ScorerBallot.vue` | ✅ Fixed |
| C10 | Vue handlers listen for `PRECEDENCE_UPDATED` but server emits `QUEUE_UPDATED` | `LiveSessionFloor.vue`, `StudentSessionView.vue` | ✅ Fixed |
| C11 | `judgerId` not passed from Django to scorer/PO templates | `views.py`, `congress_scorer.html`, `congress_po.html` | ✅ Fixed |
| C12 | Dashboard calls `/api/congress/docket/?tournament_id=X` but docket router only has `/docket/legislation/` | `CongressDashboard.vue` | ✅ Fixed |

### WARNING (would cause runtime errors in specific flows)

| # | Issue | Files | Status |
|---|-------|-------|--------|
| W01 | Rankings send `rank` but schema expects `rank_position` | `ScorerBallot.vue`, `ParliamentarianPanel.vue` | ✅ Fixed |
| W02 | `list_sessions` router only filters by `chamber_id`, but dashboard calls `?tournament_id=X` | `nekocongress/routers/sessions.py` | ✅ Fixed |
| W03 | CongressStandings uses `config.congressTournamentId` which is never set from Django | `CongressStandings.vue` | ✅ Fixed (resolves via API) |
| W04 | `callVote()` missing `docket_item_id`; `recordVote()` missing `docket_item_id`, `aff_votes`, `neg_votes` | `LiveSessionFloor.vue` | ✅ Fixed |
| W05 | `NEKOCONGRESS_URL` and `NEKOCONGRESS_API_KEY` not defined in Django settings | `settings/core.py` | ✅ Fixed |
| W06 | PO score body sends `po_legislator_id` but schema expects `hour_number` | `ScorerBallot.vue`, `ParliamentarianPanel.vue` | ✅ Fixed |
| W07 | Unused imports (`Adjudicator`, `Speaker`) in views.py | `views.py` | ✅ Fixed |

### MINOR / INFO (no runtime impact, noted for awareness)

| # | Issue | Note |
|---|-------|------|
| M01 | `ScorerBallot.vue` `scoreMin`/`scoreMax` defaults (1–8) may not match tournament config (0–10 in schema) | Works with defaults; tournament config can override |
| M02 | `ParliamentarianPanel.vue` PO evaluation uses `poLegislatorId` from config but it's never set; the `v-if="poLegislatorId"` guard protects against errors | Benign — the section simply won't show |
| M03 | `congress_events` Django app has no models.py (pure proxy to FastAPI) | By design — all data is in nekocongress DB schema |

---

## Files Modified (Complete List)

### Django / Tabbycat
1. `tabbycat/settings/core.py` — Added `congress_events` to TABBYCAT_APPS; added `NEKOCONGRESS_URL`/`NEKOCONGRESS_API_KEY` env vars
2. `tabbycat/congress_events/apps.py` — **New file**: Django AppConfig
3. `tabbycat/congress_events/views.py` — Added `judge_id` to scorer/PO views; cleaned unused imports
4. `tabbycat/tournaments/urls.py` — Added congress public + admin URL includes
5. `tabbycat/templates/congress_events/congress_scorer.html` — Added `judgerId` to JS config
6. `tabbycat/templates/congress_events/congress_po.html` — Added `judgerId` to JS config

### Vue Components
7. `tabbycat/templates/congress/LiveSessionFloor.vue` — Fixed 7 API paths, chamberId from session, event name, vote bodies
8. `tabbycat/templates/congress/ScorerBallot.vue` — Fixed score POST path, speeches path, loadScores response handling, rank→rank_position, PO score body, chamberId
9. `tabbycat/templates/congress/StudentSessionView.vue` — Fixed speeches path, chamberId, event name
10. `tabbycat/templates/congress/ParliamentarianPanel.vue` — Fixed speeches path, rank→rank_position, PO score body
11. `tabbycat/templates/congress/CongressStandings.vue` — Fixed congressTournamentId resolution via API, chambers query param
12. `tabbycat/templates/congress/CongressDashboard.vue` — Fixed docket API path

### nekocongress FastAPI
13. `nekocongress/nekocongress/routers/floor.py` — Fixed docket_status enum values
14. `nekocongress/nekocongress/routers/sessions.py` — Added `tournament_id` filter to `list_sessions`

### Infrastructure
15. `config/nginx.conf.erb` — Added nekocongress upstream + /api/congress/ location block
16. `config/nginx-docker.conf` — Added nekocongress upstream + /api/congress/ location block
17. `docker-compose.yml` — Added nekocongress service + nginx dependency
18. `nekocongress/Dockerfile` — **New file**: Python 3.12, port 8002

---

## Deployment Guide

### Prerequisites
- Heroku CLI installed and authenticated
- PostgreSQL database with `congress_events` schema (run the SQL migration)
- Redis instance (Heroku Redis or similar)

### Step 1: Run the SQL Migration

```bash
# Connect to your Heroku Postgres instance
heroku pg:psql -a your-nekocongress-app < nekocongress/migrations/001_create_congress_events_schema.sql
```

### Step 2: Deploy nekocongress as a Heroku App

```bash
# From the repo root
cd nekocongress

# Create the Heroku app (if not already created)
heroku create your-nekocongress-app

# Set runtime
heroku buildpacks:set heroku/python -a your-nekocongress-app

# Set config vars
heroku config:set \
  NEKOCONGRESS_DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/dbname" \
  NEKOCONGRESS_REDIS_URL="redis://host:6379/4" \
  NEKOCONGRESS_CELERY_BROKER_URL="redis://host:6379/5" \
  NEKOCONGRESS_CORS_ORIGINS="https://your-tabbycat-app.herokuapp.com" \
  NEKOCONGRESS_API_KEY="your-secure-api-key" \
  DJANGO_SECRET_KEY="same-as-tabbycat-secret-key" \
  -a your-nekocongress-app

# Deploy using git subtree push
cd ..
git subtree push --prefix nekocongress heroku-nekocongress main
```

### Step 3: Configure Tabbycat Environment

On the **Tabbycat** Heroku app, set:

```bash
heroku config:set \
  NEKOCONGRESS_URL="https://your-nekocongress-app.herokuapp.com" \
  NEKOCONGRESS_API_KEY="your-secure-api-key" \
  NEKOCONGRESS_HOST="your-nekocongress-app.herokuapp.com" \
  NEKOCONGRESS_PORT="443" \
  -a your-tabbycat-app
```

### Step 4: Deploy Tabbycat

```bash
git push heroku main
```

### Step 5: Verify

1. **Health check**: `curl https://your-nekocongress-app.herokuapp.com/api/congress/health`
2. **Admin access**: Navigate to `https://your-tabbycat-app.herokuapp.com/<tournament>/admin/congress/`
3. **WebSocket**: Open browser DevTools → Network → WS tab → verify connection to `/api/congress/ws/chamber/{id}/`

### Docker (Local Development)

```bash
docker-compose up --build
# Access at http://localhost:8000
# nekocongress at http://localhost:8002
# Nginx proxies /api/congress/* → nekocongress:8002
```

### Environment Variable Reference

| Variable | App | Description |
|----------|-----|-------------|
| `NEKOCONGRESS_DATABASE_URL` | nekocongress | Async Postgres connection string |
| `NEKOCONGRESS_REDIS_URL` | nekocongress | Redis for pub/sub (db 4) |
| `NEKOCONGRESS_CELERY_BROKER_URL` | nekocongress | Celery broker Redis (db 5) |
| `NEKOCONGRESS_CORS_ORIGINS` | nekocongress | Comma-separated allowed origins |
| `NEKOCONGRESS_API_KEY` | nekocongress | API key for auth |
| `DJANGO_SECRET_KEY` | nekocongress | Shared with Tabbycat for JWT verification |
| `NEKOCONGRESS_URL` | tabbycat | Full URL to nekocongress service |
| `NEKOCONGRESS_API_KEY` | tabbycat | API key passed to nekocongress |
