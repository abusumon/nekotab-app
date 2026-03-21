# NekoTab Full-Site Route Audit Prompt

> Copy everything below the line into any AI assistant, crawler tool, or Playwright test framework.

---

You are a production reliability auditor and QA engineer for **NekoTab** — a live, multi-tenant debate tabulation platform at `https://nekotab.app`. Tournaments run on subdomains like `https://dc-2026.nekotab.app`. This is mission-critical infrastructure — broken pages during live tournaments cause operational disruption for hundreds of participants.

## Architecture Context

- **Stack**: Django 5.2 + Vue 2 + PostgreSQL + Redis + Nginx (Heroku)
- **Subdomain routing**: Middleware rewrites `<slug>.nekotab.app/path` → `/<slug>/path` internally. Every tournament-scoped URL below is accessible both as `https://nekotab.app/<slug>/...` and `https://<slug>.nekotab.app/...`
- **Three permission tiers**: Public (no login), Admin (tournament owner/staff), Assistant (limited staff)
- **Three tournament types**: Standard debate, Individual Events (IE/Speech), Congressional Debate
- **Microservices**: nekospeech (FastAPI on port 8001 for IE), nekocongress (FastAPI on port 8002 for Congress)
- **Auth**: Django sessions, shared across subdomains via `.nekotab.app` cookie domain

## Task

Systematically test **every route** listed below. For each URL:

1. **GET the URL** (or POST where noted)
2. **Record**: HTTP status code, redirect chain, response time, content-type
3. **Classify the result**:
   - `200` → Check for soft failures (blank body, missing Vue mount, JS errors, empty tables)
   - `301/302` → Record destination. If redirect loops or goes to wrong place, flag it
   - `403` → Expected for admin routes when not logged in. But if a **public navigation link** points to a 403 route, flag as **UX bug**
   - `404` → Broken link
   - `500` → Server crash (CRITICAL)
   - Timeout (>10s) → Performance issue

## Route Inventory — Complete List

### 1. Root Site Pages (https://nekotab.app)

| Method | Path | Name | Auth | Expected |
|--------|------|------|------|----------|
| GET | `/` | Homepage | Public | 200 |
| GET | `/start/` | Blank site start | Public | 200 |
| GET | `/style/` | Style guide | Public | 200 |
| GET | `/create/` | Create tournament | Login | 200 or 302→login |
| GET | `/create/ie/` | Create IE tournament | Login | 200 or 302→login |
| GET | `/create/congress/` | Create congress tournament | Login | 200 or 302→login |
| GET | `/register/tournament/` | Register + create tournament | Public | 200 |
| GET | `/register/organization/` | Register + create org | Public | 200 |
| GET | `/for-organizers/` | Marketing page | Public | 200 |
| GET | `/free-debate-tab-software/` | SEO page | Public | 200 |
| GET | `/bp-debate-tabulation/` | SEO page | Public | 200 |
| GET | `/tabroom-alternative/` | SEO page | Public | 200 |
| GET | `/sitemap.xml` | Sitemap | Public | 200 XML |
| GET | `/robots.txt` | Robots | Public | 200 text |
| GET | `/ads.txt` | Ads | Public | 200 text |
| GET | `/googlee0a2b1e83278e880.html` | Verification | Public | 200 |
| GET | `/google4a7d5456478d704b.html` | Verification | Public | 200 |
| GET | `/api/` | API root | Public | 200 JSON |
| GET | `/api/v1/` | API v1 root | Public | 200 JSON |
| GET | `/api/schema/` | OpenAPI schema | Public | 200 |
| GET | `/api/schema/redoc/` | API docs | Public | 200 |

### 2. Authentication & Accounts (https://nekotab.app/accounts/)

| Method | Path | Auth | Expected |
|--------|------|------|----------|
| GET | `/accounts/login/` | Public | 200 |
| GET | `/accounts/signup/` | Public | 200 |
| GET | `/accounts/password_reset/` | Public | 200 |
| GET | `/accounts/password_reset/done/` | Public | 200 |
| GET | `/accounts/logout/` | Login | 302→homepage |

### 3. Global Features (https://nekotab.app)

| Method | Path | Name | Auth | Expected |
|--------|------|------|------|----------|
| GET | `/forum/` | Forum home | Public | 200 |
| GET | `/motions-bank/` | Motion Bank home | Public | 200 |
| GET | `/motions-bank/doctor/` | Motion Doctor | Public | 200 |
| GET | `/passport/` | Passport directory | Public | 200 |
| GET | `/organizations/` | Org list | Login | 200 or 302 |
| GET | `/campaigns/` | Campaign list | Login | 200 or 302 |
| GET | `/analytics/` | Analytics dashboard | Superuser | 200 or 302/403 |
| GET | `/notifications/status/` | Email status | Login | 200 or 302 |

### 4. Tournament-Scoped URLs

**Test with a real tournament slug** (e.g., `dc-2026`). Test both:
- Path-based: `https://nekotab.app/dc-2026/...`
- Subdomain-based: `https://dc-2026.nekotab.app/...`

#### 4A. Public Tournament Pages

| Method | Path (relative to tournament root) | Name | Expected |
|--------|-----------------------------------|------|----------|
| GET | `/` | Tournament homepage | 200 |
| GET | `/schedule/` | Public schedule | 200 |
| GET | `/draw/` | Current round draw | 200 (if draw released) |
| GET | `/draw/round/1/` | Draw for round 1 | 200 (if released) |
| GET | `/draw/sides/` | Side allocations | 200 |
| GET | `/results/` | Public results index | 200 |
| GET | `/results/round/1/` | Results for round 1 | 200 |
| GET | `/motions/` | Released motions | 200 |
| GET | `/motions/statistics/` | Motion statistics | 200 |
| GET | `/participants/list/` | Participant list | 200 |
| GET | `/participants/institutions/` | Institution list | 200 |
| GET | `/participants/team/1/` | Team record (pk=1) | 200 or 404 |
| GET | `/participants/adjudicator/1/` | Adjudicator record | 200 or 404 |
| GET | `/standings/current-standings/` | Current team standings | 200 |
| GET | `/standings/team/` | Team tab | 200 |
| GET | `/standings/speaker/` | Speaker tab | 200 |
| GET | `/standings/replies/` | Reply tab | 200 |
| GET | `/standings/adjudicators/` | Adj tab | 200 |
| GET | `/standings/diversity/` | Diversity stats | 200 |
| GET | `/break/` | Break index | 200 |
| GET | `/break/adjudicators/` | Breaking adjs | 200 |
| GET | `/feedback/progress/` | Feedback progress | 200 |
| GET | `/checkins/status/people/` | Check-in status | 200 |
| GET | `/registration/` | Registration landing | 200 |

#### 4B. Congress Public Pages (if tournament type is Congress)

| Method | Path | Name | Expected |
|--------|------|------|----------|
| GET | `/congress/standings/` | Public standings | 200 |
| GET | `/congress/student/session/1/` | Student session view | 200 or 404 |

#### 4C. IE Public Pages (if tournament type is IE)

| Method | Path | Name | Expected |
|--------|------|------|----------|
| GET | `/ie/` | Public IE dashboard | 200 |
| GET | `/ie/1/standings/` | IE event standings | 200 or 404 |

#### 4D. Admin Tournament Pages (require login + admin permission)

| Method | Path | Name | Expected |
|--------|------|------|----------|
| GET | `/admin/` | Admin home | 200 or 302→login |
| GET | `/admin/configure/` | Tournament config | 200 |
| GET | `/admin/options/` | Options index | 200 |
| GET | `/admin/participants/list/` | Admin participant list | 200 |
| GET | `/admin/participants/institutions/` | Admin institutions | 200 |
| GET | `/admin/participants/code-names/` | Code names | 200 |
| GET | `/admin/participants/eligibility/` | Speaker eligibility | 200 |
| GET | `/admin/participants/team/1/` | Admin team record | 200 or 404 |
| GET | `/admin/participants/adjudicator/1/` | Admin adj record | 200 or 404 |
| GET | `/admin/import/simple/` | Simple importer | 200 |
| GET | `/admin/import/export/` | Export page | 200 |
| GET | `/admin/privateurls/` | Private URLs list | 200 |
| GET | `/admin/availability/round/1/` | Availability for R1 | 200 or 404 |
| GET | `/admin/availability/round/1/adjudicators/` | Adj availability | 200 |
| GET | `/admin/availability/round/1/teams/` | Team availability | 200 |
| GET | `/admin/availability/round/1/venues/` | Venue availability | 200 |
| GET | `/admin/draw/round/1/` | Admin draw for R1 | 200 or 404 |
| GET | `/admin/draw/round/1/details/` | Draw details | 200 |
| GET | `/admin/draw/round/1/position-balance/` | Position balance | 200 |
| GET | `/admin/draw/round/1/display/` | Draw display | 200 |
| GET | `/admin/draw/round/current/display-by-venue/` | Current draw by venue | 200 |
| GET | `/admin/draw/round/current/display-by-team/` | Current draw by team | 200 |
| GET | `/admin/draw/sides/` | Side allocations | 200 |
| GET | `/admin/results/round/1/` | Admin results for R1 | 200 or 404 |
| GET | `/admin/motions/round/1/edit/` | Edit motions R1 | 200 or 404 |
| GET | `/admin/motions/round/1/display/` | Display motions R1 | 200 |
| GET | `/admin/motions/statistics/` | Motion stats | 200 |
| GET | `/admin/feedback/` | Feedback overview | 200 |
| GET | `/admin/feedback/progress/` | Feedback progress | 200 |
| GET | `/admin/feedback/latest/` | Latest feedback | 200 |
| GET | `/admin/feedback/important/` | Important feedback | 200 |
| GET | `/admin/feedback/comments/` | Feedback comments | 200 |
| GET | `/admin/feedback/source/list/` | By source | 200 |
| GET | `/admin/feedback/target/list/` | By target | 200 |
| GET | `/admin/feedback/add/` | Add feedback index | 200 |
| GET | `/admin/standings/round/1/` | Admin standings R1 | 200 or 404 |
| GET | `/admin/standings/round/1/team/` | Team standings R1 | 200 |
| GET | `/admin/standings/round/1/speaker/` | Speaker standings R1 | 200 |
| GET | `/admin/standings/round/1/reply/` | Reply standings R1 | 200 |
| GET | `/admin/standings/round/1/diversity/` | Diversity R1 | 200 |
| GET | `/admin/break/` | Break index | 200 |
| GET | `/admin/break/adjudicators/` | Breaking adjs | 200 |
| GET | `/admin/break/eligibility/` | Break eligibility | 200 |
| GET | `/admin/checkins/prescan/` | Check-in scanner | 200 |
| GET | `/admin/checkins/status/people/` | People check-in status | 200 |
| GET | `/admin/checkins/status/venues/` | Venue check-in status | 200 |
| GET | `/admin/checkins/identifiers/` | Check-in identifiers | 200 |
| GET | `/admin/allocations/conflicts/adjudicator-team/` | Adj-team conflicts | 200 |
| GET | `/admin/allocations/conflicts/adjudicator-adjudicator/` | Adj-adj conflicts | 200 |
| GET | `/admin/allocations/conflicts/adjudicator-institution/` | Adj-inst conflicts | 200 |
| GET | `/admin/allocations/conflicts/team-institution/` | Team-inst conflicts | 200 |
| GET | `/admin/allocations/panels/edit/` | Panel editor | 200 |
| GET | `/admin/printing/round/1/scoresheets/` | Print scoresheets | 200 |
| GET | `/admin/printing/round/1/feedback/` | Print feedback | 200 |
| GET | `/admin/printing/urls_sheets/teams/` | Print team URLs | 200 |
| GET | `/admin/printing/urls_sheets/adjudicators/` | Print adj URLs | 200 |
| GET | `/admin/users/` | Admin user management | 200 |
| GET | `/admin/notifications/` | Admin notifications | 200 |
| GET | `/admin/registration/institutions/` | Reg institutions | 200 |
| GET | `/admin/registration/teams/` | Reg teams | 200 |
| GET | `/admin/registration/adjudicators/` | Reg adjudicators | 200 |

#### 4E. Congress Admin Pages

| Method | Path | Name | Expected |
|--------|------|------|----------|
| GET | `/admin/congress/` | Congress dashboard | 200 |
| GET | `/admin/congress/setup/` | Congress setup wizard | 200 |
| GET | `/admin/congress/docket/` | Docket manager | 200 |
| GET | `/admin/congress/chambers/` | Chamber manager | 200 |
| GET | `/admin/congress/session/1/` | Session view | 200 or 404 |
| GET | `/admin/congress/session/1/scorer/` | Scorer view | 200 or 404 |
| GET | `/admin/congress/standings/` | Admin standings | 200 |
| GET | `/admin/congress/session/1/po/` | PO view | 200 or 404 |

#### 4F. IE (Speech Events) Admin Pages

| Method | Path | Name | Expected |
|--------|------|------|----------|
| GET | `/admin/ie/` | IE dashboard | 200 |
| GET | `/admin/ie/setup/` | IE setup wizard | 200 |
| GET | `/admin/ie/prep/` | Tournament prep | 200 |
| GET | `/admin/ie/prep/all/` | All prep data (JSON) | 200 JSON |
| GET | `/admin/ie/prep/institutions/` | Prep institutions (JSON) | 200 JSON |
| GET | `/admin/ie/prep/speakers/` | Prep speakers (JSON) | 200 JSON |
| GET | `/admin/ie/prep/judges/` | Prep judges (JSON) | 200 JSON |
| GET | `/admin/ie/1/entries/` | Entry manager | 200 or 404 |
| GET | `/admin/ie/1/draw/1/` | Room draw | 200 or 404 |
| GET | `/admin/ie/1/standings/` | IE standings | 200 or 404 |
| GET | `/admin/ie/1/finalists/` | Finalists | 200 or 404 |
| GET | `/admin/ie/1/judge-links/1/page/` | Judge links page | 200 or 404 |

#### 4G. Assistant Pages

| Method | Path | Name | Expected |
|--------|------|------|----------|
| GET | `/assistant/` | Assistant home | 200 or 302 |
| GET | `/assistant/draw/display/` | Draw display | 200 |
| GET | `/assistant/results/` | Results list | 200 |
| GET | `/assistant/feedback/add/` | Add feedback | 200 |
| GET | `/assistant/checkins/prescan/` | Check-in scan | 200 |
| GET | `/assistant/checkins/status/people/` | Check-in status | 200 |
| GET | `/assistant/checkins/status/venues/` | Venue status | 200 |
| GET | `/assistant/participants/list/` | Participant list | 200 |
| GET | `/assistant/participants/institutions/` | Institutions | 200 |
| GET | `/assistant/motions/display/` | Motions display | 200 |
| GET | `/assistant/printing/scoresheets/` | Print scoresheets | 200 |
| GET | `/assistant/printing/feedback/` | Print feedback | 200 |

### 5. REST API Endpoints (JSON)

**Global** (`/api/v1/`):
| Method | Path | Expected |
|--------|------|----------|
| GET | `/api/v1/institutions` | 200 JSON |
| GET | `/api/v1/users` | 200 JSON (auth) |
| GET | `/api/v1/users/me` | 200 JSON (auth) or 401 |

**Tournament-scoped** (`/api/v1/tournaments/<slug>/`):
| Method | Path | Expected |
|--------|------|----------|
| GET | `/api/v1/tournaments/<slug>/` | 200 JSON |
| GET | `/api/v1/tournaments/<slug>/teams` | 200 JSON |
| GET | `/api/v1/tournaments/<slug>/adjudicators` | 200 JSON |
| GET | `/api/v1/tournaments/<slug>/speakers` | 200 JSON |
| GET | `/api/v1/tournaments/<slug>/venues` | 200 JSON |
| GET | `/api/v1/tournaments/<slug>/motions` | 200 JSON |
| GET | `/api/v1/tournaments/<slug>/rounds` | 200 JSON |
| GET | `/api/v1/tournaments/<slug>/rounds/1/pairings` | 200 JSON |
| GET | `/api/v1/tournaments/<slug>/rounds/1/availabilities` | 200 JSON |
| GET | `/api/v1/tournaments/<slug>/feedback` | 200 JSON |
| GET | `/api/v1/tournaments/<slug>/feedback-questions` | 200 JSON |
| GET | `/api/v1/tournaments/<slug>/break-categories` | 200 JSON |
| GET | `/api/v1/tournaments/<slug>/speaker-categories` | 200 JSON |
| GET | `/api/v1/tournaments/<slug>/venue-categories` | 200 JSON |
| GET | `/api/v1/tournaments/<slug>/teams/standings` | 200 JSON |
| GET | `/api/v1/tournaments/<slug>/speakers/standings` | 200 JSON |
| GET | `/api/v1/tournaments/<slug>/institutions` | 200 JSON |
| GET | `/api/v1/tournaments/<slug>/me` | 200 JSON (auth) |

### 6. Microservice Proxied Endpoints (via Nginx)

| Method | Path | Service | Expected |
|--------|------|---------|----------|
| GET | `/api/ie/docs` | nekospeech | 200 HTML |
| GET | `/api/ie/health` | nekospeech | 200 JSON |
| GET | `/api/congress/docs` | nekocongress | 200 HTML |
| GET | `/api/congress/health` | nekocongress | 200 JSON |

## Edge Case Tests

### Subdomain Routing

| Test | URL | Expected |
|------|-----|----------|
| Valid subdomain | `https://dc-2026.nekotab.app/` | 200 (tournament home) |
| Invalid subdomain | `https://nonexistent.nekotab.app/` | Custom 404 page |
| Reserved subdomain | `https://admin.nekotab.app/` | Redirect or 404 |
| Reserved subdomain | `https://www.nekotab.app/` | Redirect to nekotab.app or 200 |
| Reserved subdomain | `https://api.nekotab.app/` | Redirect or 404 |
| Case sensitivity | `https://DC-2026.nekotab.app/` | Same as lowercase (DNS is case-insensitive) |
| Double slug | `https://dc-2026.nekotab.app/dc-2026/admin/` | Should NOT double-prefix. Should work same as `/admin/` |

### Path Edge Cases

| Test | URL | Expected |
|------|-----|----------|
| Trailing slash | `/admin/congress` vs `/admin/congress/` | Both should work (301 or 200) |
| Nonexistent round | `/admin/draw/round/999/` | 404 (not 500) |
| Nonexistent team PK | `/participants/team/999999/` | 404 (not 500) |
| Nonexistent adj PK | `/participants/adjudicator/999999/` | 404 (not 500) |
| Zero round | `/admin/draw/round/0/` | 404 (not 500) |
| Negative round | `/admin/draw/round/-1/` | 404 (not 500) |
| String where int expected | `/admin/congress/session/abc/` | 404 (not 500) |
| SQL injection attempt | `/participants/team/1' OR 1=1/` | 404 (not 500, no leak) |
| XSS in path | `/participants/team/<script>alert(1)</script>/` | 404, no reflection |

### Cross-Feature Routing

| Test | Description | Expected |
|------|-------------|----------|
| Public link → protected page | Click every link on public tournament page. None should 403. | No 403 from public nav |
| Admin nav completeness | Every sidebar link in admin resolves | No 404 from admin sidebar |
| Mobile nav | Every link in mobile menu resolves | No 404 |
| Footer links | Every footer link resolves | No 404 |
| Breadcrumb links | Every breadcrumb link resolves | No 404 |

## Output Format

### Critical Errors (500)
| URL | Method | Error | Referrer |
|-----|--------|-------|----------|

### Broken Links (404)
| URL | Method | Referrer | Note |
|-----|--------|----------|------|

### UX Bugs (public link → 403)
| Public Page | Link Text | Destination | Issue |
|-------------|-----------|-------------|-------|

### Soft Failures (200 but broken content)
| URL | Issue | Details |
|-----|-------|---------|

### Redirect Issues (loops, wrong destination)
| URL | Chain | Issue |
|-----|-------|-------|

### Performance Issues (>5s response)
| URL | Response Time | Note |
|-----|--------------|------|

### Subdomain Routing Issues
| Subdomain | Path | Expected | Actual |
|-----------|------|----------|--------|

## Known Issues (exclude from report)

- Local SQLite migrations fail on `forum_forumthread` (ArrayField) — only affects dev, not production
- `ConsoleEmailBackend` in dev — expected, production uses Resend SMTP
- Django admin (`/database/`) requires superuser — 302→login is expected

## Priority

Focus on routes that **tournament directors and participants use during live events**:
1. Draw pages (admin + public)
2. Results entry (admin + assistant + public ballot submission)
3. Standings/tab pages
4. Check-in pages
5. Congress/IE session pages
6. Break qualification
7. Participant lists
8. Feedback entry

A broken page during a live round means hundreds of people waiting. Treat every 500 as P0.
