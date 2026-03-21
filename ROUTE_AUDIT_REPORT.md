# NekoTab Full-Site Route Audit Report

**Date:** March 21, 2026  
**Audited Domain:** `nekotab.app` and `dc-2026.nekotab.app`  
**Tournament Used:** `dc-2026`  
**Total Routes Tested:** 232  
**Auth State:** Unauthenticated (no session cookie)

---

## Executive Summary

| Category | Count |
|----------|-------|
| 200 OK | 36 |
| 301 Redirect (path→subdomain) | 122 |
| 302 Redirect (login required) | 9 |
| 401 Unauthorized (API) | 13 |
| 403 Forbidden (prefs disabled) | 22 |
| 404 Not Found | 28 |
| 405 Method Not Allowed | 1 |
| **500 Server Error** | **1** |

**Real bugs found: 3**  
**Audit document corrections needed: 9**  
**Tournament configuration issues: 22 routes**

---

## Critical Errors (500) — P0

| URL | Method | Issue | Root Cause |
|-----|--------|-------|------------|
| `https://nekotab.app/api/` | GET | 500 Server Error | Trailing slash mismatch. Route is registered as `path('api', ...)` in urls.py — canonical URL is `/api` (no slash). `/api/` triggers a 500 instead of a clean 404 or 301. |

**Fix Required:** In `tabbycat/urls.py`, change `path('api', include('api.urls'))` to `path('api/', include('api.urls'))` for Django's `APPEND_SLASH` to work correctly. Alternatively, add a redirect from `/api/` to `/api`.

**Verified:** `GET /api` (no trailing slash) returns **200** correctly.

---

## Broken Links (404)

### Real Bugs

| URL | Issue | Fix |
|-----|-------|-----|
| `/<slug>/registration/` | Missing root index view. Sub-routes (`/registration/adjudicator/`, `/registration/team/`) exist but no landing page. | Add a `RegistrationIndexView` at the registration URL root. |
| `/api/ie/docs` | FastAPI docs not accessible via nginx proxy. Health endpoint works (`/api/ie/health` → 200). | Add `root_path="/api/ie"` to nekospeech FastAPI constructor. |
| `/api/congress/docs` | Same issue for nekocongress. | Add `root_path="/api/congress"` to nekocongress FastAPI constructor. |

### Stale Routes in Audit Document (not real bugs)

| Audit URL | Correct URL | Issue |
|-----------|-------------|-------|
| `/api/v1/` | `/api/v1` | No trailing slash on API routes |
| `/api/schema/` | `/api/schema.yml` | Schema endpoint is `.yml` not `/` |
| `/api/v1/tournaments/dc-2026/` | `/api/v1/tournaments/dc-2026` | No trailing slash; also returns 404 for unauthenticated users (DRF queryset filtering) |
| `/<slug>/admin/feedback/important/` | `/<slug>/admin/feedback/important` | No trailing slash on this route |
| `/<slug>/admin/printing/urls_sheets/teams/` | `/<slug>/admin/printing/urls_sheets/teams` | No trailing slash |
| `/<slug>/admin/printing/urls_sheets/adjudicators/` | `/<slug>/admin/printing/urls_sheets/adjudicators` | No trailing slash |
| `/<slug>/admin/users/` | `/<slug>/admin/users/invite/` | No user list view exists; only `invite/` and `accept/` sub-routes |
| `/notifications/status/` | `/<slug>/admin/notifications/status/` | This is tournament-scoped, not global |

---

## UX Bugs (public link → 403)

**Root Cause:** The `dc-2026` tournament has its public page preferences **disabled** (e.g., `public_schedule`, `public_draw`, `public_results`, `public_standings`, `public_break`, `public_feedback`, `public_checkins`, `public_participants` are all `False`).

**This is a configuration issue, not a code bug.** An admin needs to enable these preferences in Tournament Options → Public Features.

| Public Page | Subdomain URL | Status | Preference Needed |
|-------------|---------------|--------|-------------------|
| Schedule | `dc-2026.nekotab.app/schedule/` | 403 | `public_schedule` |
| Draw (current) | `dc-2026.nekotab.app/draw/` | 403 | `public_draw` |
| Draw (round 1) | `dc-2026.nekotab.app/draw/round/1/` | 403 | `public_draw` |
| Side allocations | `dc-2026.nekotab.app/draw/sides/` | 403 | `public_draw` |
| Results index | `dc-2026.nekotab.app/results/` | 403 | `public_results` |
| Results (round 1) | `dc-2026.nekotab.app/results/round/1/` | 403 | `public_results` |
| Motions | `dc-2026.nekotab.app/motions/` | 403 | `public_motions` |
| Motion statistics | `dc-2026.nekotab.app/motions/statistics/` | 403 | `public_motions` |
| Participant list | `dc-2026.nekotab.app/participants/list/` | 403 | `public_participants` |
| Institution list | `dc-2026.nekotab.app/participants/institutions/` | 403 | `public_participants` |
| Team standings | `dc-2026.nekotab.app/standings/current-standings/` | 403 | `public_standings` |
| Team tab | `dc-2026.nekotab.app/standings/team/` | 403 | `public_standings` |
| Speaker tab | `dc-2026.nekotab.app/standings/speaker/` | 403 | `public_standings` |
| Reply tab | `dc-2026.nekotab.app/standings/replies/` | 403 | `public_standings` |
| Adj tab | `dc-2026.nekotab.app/standings/adjudicators/` | 403 | `public_standings` |
| Diversity stats | `dc-2026.nekotab.app/standings/diversity/` | 403 | `public_standings` |
| Break index | `dc-2026.nekotab.app/break/` | 403 | `public_break` |
| Breaking adjs | `dc-2026.nekotab.app/break/adjudicators/` | 403 | `public_break` |
| Feedback progress | `dc-2026.nekotab.app/feedback/progress/` | 403 | `public_feedback` |
| Check-in status | `dc-2026.nekotab.app/checkins/status/people/` | 403 | `public_checkins` |
| IE dashboard | `dc-2026.nekotab.app/ie/` | 403 | IE public preference |
| IE standings | `dc-2026.nekotab.app/ie/1/standings/` | 403 | IE public preference |

**Note:** Congress public routes (`/congress/standings/`, `/congress/student/session/1/`) return **200** because they bypass the preference gate — they use `TournamentMixin` directly without `PublicTournamentPageMixin`. This is inconsistent but likely intentional.

---

## Soft Failures (200 but broken content)

None detected via status code audit. A browser-level audit with JavaScript execution would be needed to detect blank Vue mounts, missing components, etc.

---

## Redirect Issues

### Expected Redirects (Working Correctly)

| Pattern | Status | Behavior |
|---------|--------|----------|
| Path-based tournament URLs (`nekotab.app/dc-2026/...`) | 301 | Correctly redirects to subdomain (`dc-2026.nekotab.app/...`) |
| Login-required pages (unauthenticated) | 302 | Correctly redirects to `/accounts/login/?next=...` |
| `/start/` when users exist | 302 → `/` | By design — only shown on fresh install |
| `/register/tournament/`, `/register/organization/` | 302 → login | By design — `LoginRequiredMixin` (audit doc incorrectly says "Public") |

### Noteworthy (Not Bugs)

| Route | Status | Note |
|-------|--------|------|
| `/accounts/logout/` | 405 | POST-only in Django 5.2+ (CSRF protection). By design. |
| Admin routes on subdomain (unauthenticated) | 404 | Intentional security feature — hides admin existence from unauthorized users. |

---

## Performance Issues (>5s response)

None found. All routes responded within 2 seconds. Typical response times:
- Static/cached pages: 250-350ms
- Database-backed pages: 300-1100ms
- Subdomain tournament homepage: ~1000-1700ms (first load, includes DB lookup)

---

## Subdomain Routing Issues

| Subdomain | Status | Analysis |
|-----------|--------|----------|
| `dc-2026.nekotab.app/` | 200 | ✅ Valid tournament |
| `nonexistent.nekotab.app/` | 404 | ✅ Custom 404 page |
| `admin.nekotab.app/` | 200 | ⚠️ Returns homepage — should either redirect to `nekotab.app` or show 404. Currently treats "admin" as a tournament slug that doesn't exist but falls through to the homepage. |
| `www.nekotab.app/` | 200 | ⚠️ Returns homepage — should redirect to `nekotab.app` for canonical URL. |
| `api.nekotab.app/` | 200 | ⚠️ Returns homepage — should redirect or 404. |
| `dc-2026.nekotab.app/dc-2026/admin/` | 404 | ✅ Double-slug correctly returns 404 (no double-prefix). |

**Recommendation:** Add `admin`, `www`, `api`, `mail`, `smtp`, `ftp`, `static`, `assets`, `cdn` to a reserved subdomain list. Either redirect to the bare domain or return a clean error.

---

## Edge Case Tests

| Test | URL | Expected | Actual | Status |
|------|-----|----------|--------|--------|
| Nonexistent round | `/admin/draw/round/999/` | 404 | 404 | ✅ PASS |
| Nonexistent team PK | `/participants/team/999999/` | 404 | 404 | ✅ PASS |
| Nonexistent adj PK | `/participants/adjudicator/999999/` | 404 | 404 | ✅ PASS |
| Zero round | `/admin/draw/round/0/` | 404 | 404 | ✅ PASS |
| Negative round | `/admin/draw/round/-1/` | 404 | 404 | ✅ PASS |
| String where int expected | `/admin/congress/session/abc/` | 404 | 404 | ✅ PASS |
| Trailing slash present | `/admin/congress/` | 200 or 302 | 301→subdomain then handled | ✅ PASS |
| No trailing slash | `/admin/congress` | 301 | 301→`/dc-2026/admin/congress/` | ✅ PASS |

**SQL injection and XSS path tests were not performed** (would require curl which was blocked).

---

## API Endpoint Summary

| Endpoint | Auth Required | Status (Unauth) | Notes |
|----------|---------------|------------------|-------|
| `/api` | No | 200 | ✅ API root works (without trailing slash) |
| `/api/v1` | No | 200 | ✅ Works (without trailing slash) |
| `/api/schema.yml` | No | 200 | ✅ OpenAPI schema |
| `/api/schema/redoc/` | No | 200 | ✅ API docs |
| `/api/v1/institutions` | Yes | 401 | Expected |
| `/api/v1/users` | Yes | 401 | Expected |
| `/api/v1/users/me` | Yes | 401 | Expected |
| `/api/v1/tournaments/dc-2026/venues` | No | 200 | ✅ Public data |
| `/api/v1/tournaments/dc-2026/rounds` | No | 200 | ✅ Public data |
| `/api/v1/tournaments/dc-2026/feedback-questions` | No | 200 | ✅ |
| `/api/v1/tournaments/dc-2026/break-categories` | No | 200 | ✅ |
| `/api/v1/tournaments/dc-2026/speaker-categories` | No | 200 | ✅ |
| `/api/v1/tournaments/dc-2026/venue-categories` | No | 200 | ✅ |
| `/api/v1/tournaments/dc-2026/me` | No | 200 | ✅ Returns anonymous context |
| `/api/v1/tournaments/dc-2026/teams` | Yes | 401 | Expected |
| `/api/v1/tournaments/dc-2026/adjudicators` | Yes | 401 | Expected |
| `/api/v1/tournaments/dc-2026/speakers` | Yes | 401 | Expected |
| `/api/v1/tournaments/dc-2026/motions` | Yes | 401 | Expected |
| `/api/v1/tournaments/dc-2026/feedback` | Yes | 401 | Expected |
| `/api/ie/health` | No | 200 | ✅ nekospeech health |
| `/api/congress/health` | No | 200 | ✅ nekocongress health |

---

## Action Items (Prioritized)

### P0 — Fix Immediately
1. **`/api/` 500 error** — Add trailing slash to the `api` path in `urls.py`, or add a redirect rule.

### P1 — Fix Soon
2. **Missing `/registration/` index view** — Users visiting the registration root get 404. Add a landing page that lists registration options.
3. **Microservice docs 404** — Add `root_path` configuration to nekospeech and nekocongress FastAPI apps.

### P2 — Improve
4. **Reserved subdomain handling** — `admin.nekotab.app`, `www.nekotab.app`, `api.nekotab.app` return the main homepage instead of redirecting or showing an error.
5. **Trailing slash inconsistency** — Several admin routes (`feedback/important`, `printing/urls_sheets/teams`, `printing/urls_sheets/adjudicators`) don't have trailing slashes, making them inconsistent with the rest of the URL patterns. Consider adding `APPEND_SLASH`-compatible patterns.

### P3 — Audit Document Updates
6. Update the audit document to correct:
   - API URLs (remove trailing slashes)
   - `/api/schema/` → `/api/schema.yml`  
   - `/notifications/status/` → `/<slug>/admin/notifications/status/`
   - `/register/tournament/` and `/register/organization/` are Login-required (not Public)
   - `/accounts/logout/` is POST-only
   - `/<slug>/admin/users/` → `/<slug>/admin/users/invite/`

### Configuration
7. **Enable public preferences for `dc-2026`** if public pages should be visible: `public_schedule`, `public_draw`, `public_results`, `public_standings`, `public_break`, `public_feedback`, `public_checkins`, `public_participants`.
