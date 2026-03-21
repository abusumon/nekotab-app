# NekoTab — Audit Fix Implementation
## Engineering Prompt for Claude Opus 4.6 (Part 12 — Fix All Audit Issues)

---

## CONTEXT

A deep technical audit of nekotab.app was completed. It found 4 critical bugs,
7 important improvements, and 3 growth actions. Your job is to implement ALL of
them — no skipping, no deferring, no "this is out of scope."

The full audit report is in `NEKOTAB_DEEP_AUDIT.md` at the repo root.
Read it first before implementing anything.

---

## MANDATORY READING — DO THIS BEFORE ANY CHANGES

Read these files completely before touching anything:

```
NEKOTAB_DEEP_AUDIT.md                              — full audit findings
tabbycat/templates/nekotab_home.html               — homepage template (standalone, ~2000 lines, NOT extending base.html)
tabbycat/settings/core.py                          — Django settings
tabbycat/settings/heroku.py                        — Heroku-specific settings
config/nginx.conf.erb                              — Production nginx config (Heroku ERB template)
config/nginx-docker.conf                           — Docker nginx config (NO autoindex — different from production)
tabbycat/urls.py                                   — Root URL configuration
tabbycat/sitemaps.py                               — Main sitemap (StaticViewSitemap, TournamentSitemap, MotionBankSitemap)
tabbycat/content/sitemaps.py                       — Content sitemaps (LearnArticleSitemap, TrustPagesSitemap)
tabbycat/static/css/landing.css                    — Homepage CSS (uses `em-*` class prefix, NOT Bootstrap)
tabbycat/static/js/landing.js                      — Homepage JS
tabbycat/templates/base.html                       — Base template (used by all NON-homepage pages)
tabbycat/templates/footer.html                     — Footer template (included by base.html via {% include %})
tabbycat/templates/registration/login.html         — Login page (extends base.html)
tabbycat/users/templates/public_signup.html         — Public signup template
tabbycat/users/urls.py                             — User auth URLs
tabbycat/api/urls.py                               — API URL config
tabbycat/api/views.py                              — API views (find APIRootView)
tabbycat/templates/js-bundles/main.js              — Vue entry point (has 20+ lazy imports already)
vue.config.js                                      — Vue build configuration
Pipfile                                            — Python dependencies
```

### CRITICAL CODEBASE FACTS TO KNOW BEFORE STARTING

1. **Homepage is standalone.** `nekotab_home.html` does NOT extend `base.html`.
   It has its own `<head>`, nav, footer. CSS uses custom `em-*` class prefix
   (NOT Bootstrap utilities). All homepage changes must use `em-*` classes or
   create new ones in `landing.css`.

2. **Tournament pages use `base.html` + `footer.html`.** The footer is a
   separate template at `tabbycat/templates/footer.html`, included via
   `{% include "footer.html" %}`. This is where "Powered by NekoTab" changes go.

3. **URL names already exist.** Key URL names:
   - `'tournament-create'` → `/create/` (requires auth)
   - `'register-tournament'` → `/register/tournament/` (Phase 7, handles signup + creation)
   - `'register-organization'` → `/register/organization/`
   - `'signup'` → `/accounts/signup/`
   - `'login'` → `/accounts/login/`
   - `'tabbycat-index'` → `/` (homepage)
   The homepage hero uses `{% url 'tournament-create' %}` and
   `{% url 'register-organization' %}` as Django template tags.

4. **Login uses Django's built-in `LoginView`.** The user URL conf includes
   `django.contrib.auth.urls`, so the login view is standard Django. This means
   `django-axes` integrates automatically with no custom view changes needed.

5. **Vue lazy imports already exist.** `main.js` has 20+ `() => import(...)`
   statements. The issue is that `vue.config.js` overrides this with
   `config.optimization.splitChunks(false)`. Removing that line is the only
   code-splitting fix needed.

6. **`TournamentSitemap` already exists** in `tabbycat/sitemaps.py`. It filters
   `Tournament.objects.filter(active=True, is_listed=True)` and uses
   `f"/{obj.slug}/"` for location. Do NOT duplicate this class.

7. **Django already sets most security headers** via `SecurityMiddleware` in
   `core.py`: HSTS (31536000s), X-Frame-Options (SAMEORIGIN), X-Content-Type-
   Options (nosniff), Referrer-Policy (strict-origin-when-cross-origin). What's
   MISSING is: Content-Security-Policy and Permissions-Policy.

8. **Nginx `add_header` inheritance gotcha.** If ANY `add_header` directive
   appears in a `location` block, ALL server-level `add_header` directives are
   NOT inherited into that block. The `/static/` block already has
   `add_header Cache-Control "public"`, so server-level security headers
   would NOT apply to static files. Solution: repeat security headers in every
   location block that uses its own `add_header`, OR add CSP via Django.

9. **The FAQ says "simple one-time fee"** — the `<details>` answer for "Is it
   free to use?" says *"You can also use our hosted service for a simple
   one-time fee."* This **contradicts** the "free forever" messaging. The JSON-LD
   `FAQPage` structured data has the same wrong text. Both must be corrected.

10. **The `tabbycat/templates/pages/` directory does NOT exist.** It must be
    created for SEO landing pages.

After reading all files, state: "Read [N] files. Beginning fixes." Then start Fix 1.

---

## THE 13 FIXES — IMPLEMENT IN THIS EXACT ORDER

---

### FIX 1 — C1: Fix sitemap domain (example.com → nekotab.app)

**The problem:** Django's `django_site` table still has `example.com` as the
domain. Every URL in `/sitemap.xml` points to `https://example.com/...`. Google
cannot index any content via sitemap.

**What to do:**

1. Confirm `'django.contrib.sites'` is in `INSTALLED_APPS` (it is — `core.py`).
   Confirm `SITE_ID = 1` is in `core.py` (it is — line 349).

2. Create a data migration in the `content` app, since that app already has
   data migrations (`0002_seed_content.py`, `0003_expand_articles.py`, etc.):

```python
# Create: tabbycat/content/migrations/0005_set_site_domain.py

from django.db import migrations


def set_site_domain(apps, schema_editor):
    Site = apps.get_model('sites', 'Site')
    Site.objects.update_or_create(
        id=1,
        defaults={
            'domain': 'nekotab.app',
            'name': 'NekoTab',
        },
    )


def revert_site_domain(apps, schema_editor):
    Site = apps.get_model('sites', 'Site')
    Site.objects.filter(id=1).update(
        domain='example.com',
        name='example.com',
    )


class Migration(migrations.Migration):
    dependencies = [
        ('content', '0004_add_more_articles'),
        ('sites', '0002_alter_domain_unique'),
    ]
    operations = [
        migrations.RunPython(set_site_domain, revert_site_domain),
    ]
```

**Why `content` app:** It already has data migrations (fixtures, articles). The
`content` app is the right home for site-level configuration seeds. Do NOT put
this in `tabbycat/migrations/` — that is not a Django app directory and has no
`__init__.py`.

**Verify migration number:** Check `tabbycat/content/migrations/` for the latest
numbered file. If the latest is `0004_add_more_articles.py`, name this
`0005_set_site_domain.py`. If another migration has been added since, adjust.

**Verification after deploy:**
```bash
python manage.py migrate
python manage.py shell -c "from django.contrib.sites.models import Site; print(Site.objects.get_current().domain)"
# Must print: nekotab.app
```

⚠️ **MANUAL STEP REQUIRED AFTER DEPLOY:**
```bash
heroku run python manage.py migrate --app <MAIN-APP>
```

---

### FIX 2 — C2: Remove autoindex from nginx static block

**The problem:** `autoindex on;` in `config/nginx.conf.erb` line ~330 allows
anyone to browse the entire `/static/` directory tree.

**What to do:**

1. Read `config/nginx.conf.erb` — find the `location /static/` block.
2. Remove the `autoindex on;` line entirely.
3. **`config/nginx-docker.conf` does NOT have `autoindex on;`** — no change needed
   there. Verify this by reading the file and confirming the `/static/` block
   only has `alias`, `access_log off`, `add_header`, and `expires`.

**Production nginx change — the ONLY change in this block:**

Before:
```nginx
location /static/ {
    alias /app/tabbycat/staticfiles/;
    autoindex on;
    access_log off;
    add_header Cache-Control "public";
    expires 7d;
    etag on;
}
```

After:
```nginx
location /static/ {
    alias /app/tabbycat/staticfiles/;
    access_log off;
    add_header Cache-Control "public";
    expires 7d;
    etag on;
}
```

**Do NOT change any other nginx directives.** Static files still serve normally —`autoindex` only controls directory listing, not file serving.

---

### FIX 3 — C3: Add brute-force protection to login

**The problem:** Zero rate limiting on the login form. Unlimited credential
stuffing attempts possible against `/accounts/login/`.

**Key fact:** Login uses Django's built-in `LoginView` (via
`path('', include('django.contrib.auth.urls'))` in `tabbycat/users/urls.py`).
`django-axes` hooks into Django's `authenticate()` call automatically — no
custom view changes needed.

**What to do:**

1. Add `django-axes` to `Pipfile` under `[packages]`:
   ```
   django-axes = "*"
   ```

2. Add `'axes'` to `INSTALLED_APPS` in `tabbycat/settings/core.py`.
   Place it AFTER `'django.contrib.auth'` (it needs auth to be loaded first):
   ```python
   INSTALLED_APPS = (
       'daphne', 'jet', 'utils.admin_site.NekoTabAdminConfig',
       'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions',
       'django.contrib.sitemaps', 'django.contrib.sites', 'django.contrib.redirects',
       'axes',  # ← Add here, after auth
       # ... rest unchanged
   ```

3. Add `AxesStandaloneBackend` as the FIRST entry in `AUTHENTICATION_BACKENDS`.
   The current config is:
   ```python
   AUTHENTICATION_BACKENDS = [
       'utils.admin_site.TournamentAdminBackend',
       'django.contrib.auth.backends.ModelBackend',
   ]
   ```

   Change to:
   ```python
   AUTHENTICATION_BACKENDS = [
       'axes.backends.AxesStandaloneBackend',  # Brute-force gate (must be first)
       'utils.admin_site.TournamentAdminBackend',
       'django.contrib.auth.backends.ModelBackend',
   ]
   ```

   **Why first:** `AxesStandaloneBackend` must be first so it can short-circuit
   authentication for locked-out IPs before other backends are tried.

4. Add `'axes.middleware.AxesMiddleware'` to `MIDDLEWARE` — it must come AFTER
   both `SessionMiddleware` and `AuthenticationMiddleware`:
   ```python
   MIDDLEWARE = [
       # ... existing middleware ...
       'django.contrib.auth.middleware.AuthenticationMiddleware',
       'django.contrib.messages.middleware.MessageMiddleware',
       'django.middleware.clickjacking.XFrameOptionsMiddleware',
       'axes.middleware.AxesMiddleware',  # ← Add here, after AuthenticationMiddleware
       'utils.middleware.SubdomainTenantMiddleware',
       # ... rest unchanged
   ]
   ```

5. Add axes configuration to `core.py` (at the end, in a new section):
   ```python
   # ==============================================================================
   # Brute-Force Protection (django-axes)
   # ==============================================================================

   AXES_FAILURE_LIMIT = 10               # Lock after 10 consecutive failures
   AXES_COOLOFF_TIME = 1                 # 1-hour lockout (integer = hours)
   AXES_LOCKOUT_PARAMETERS = [['ip_address']]  # Lock by IP (note: nested list)
   AXES_RESET_ON_SUCCESS = True          # Reset counter on successful login
   AXES_VERBOSE = False                  # Don't log every attempt
   ```

   **Note:** `AXES_LOCKOUT_PARAMETERS` uses a nested list `[['ip_address']]` in
   axes 6.x+ (the currently released version). Check the installed version — if
   <6.0, use `AXES_LOCKOUT_PARAMETERS = ['ip_address']` instead.

6. **No migration file to create manually.** Axes creates its own migration
   automatically. Just run `python manage.py migrate` after deployment.

7. **No custom login view changes needed.** Since `tabbycat/users/urls.py` uses
   `include('django.contrib.auth.urls')` which provides Django's built-in
   `LoginView`, and axes hooks into `django.contrib.auth.authenticate()`,
   it works automatically.

⚠️ **MANUAL STEPS REQUIRED AFTER DEPLOY:**
```bash
pipenv install   # or: pip install django-axes
python manage.py migrate  # creates axes tables
```

---

### FIX 4 — C4: Fix homepage CTAs — unauthenticated users to /register/tournament/

**The problem:** The "Get Started" button and "Create Single Tournament" button
link to `{% url 'tournament-create' %}` → `/create/`, which requires
authentication. New visitors hit a login wall with no prominent signup option.

**Key facts from the actual HTML:**

The hero has two CTAs:
```html
<a href="{% url 'register-organization' %}" class="em-btn em-btn--white em-btn--lg">
  Create Organization Workspace
</a>
<a href="{% url 'tournament-create' %}" class="em-btn em-btn--outline-light em-btn--lg">
  Create Single Tournament
</a>
```

The navbar has (line ~272, OUTSIDE the auth check — shows for everyone):
```html
<a href="{% url 'tournament-create' %}" class="em-btn em-btn--primary em-btn--sm">Get Started</a>
```

The "Sign in" link already exists in the navbar for logged-out users. ✅

There are **6 total** `/create/` links on the homepage:
1. Line 179: dropdown menu → `/create/`
2. Line 196: dropdown menu → `/create/ie/`
3. Line 229: hero CTA → `{% url 'register-organization' %}` (this one is fine)
4. Line 288: hero CTA → `{% url 'tournament-create' %}` ← FIX THIS
5. Line ~272: navbar "Get Started" → `{% url 'tournament-create' %}` ← FIX THIS
6. Lines 1089, 1107: footer links → `/create/`

**What to do:**

1. **Hero "Create Single Tournament" CTA** — Wrap in auth check:
   ```html
   {% if user.is_authenticated %}
     <a href="{% url 'tournament-create' %}" class="em-btn em-btn--outline-light em-btn--lg">
       <svg ...></svg>
       Create Single Tournament
     </a>
   {% else %}
     <a href="{% url 'register-tournament' %}" class="em-btn em-btn--outline-light em-btn--lg">
       <svg ...></svg>
       Create Free Tournament
     </a>
   {% endif %}
   ```

   This uses the Phase 7 `register-tournament` URL which handles both signup
   and tournament creation in one flow for unauthenticated users.

2. **Navbar "Get Started" button** — Same auth-aware logic:
   ```html
   {% if user.is_authenticated %}
     <a href="{% url 'tournament-create' %}" class="em-btn em-btn--primary em-btn--sm">Dashboard</a>
   {% else %}
     <a href="{% url 'register-tournament' %}" class="em-btn em-btn--primary em-btn--sm">Get Started Free</a>
   {% endif %}
   ```

3. **Footer links** — The footer `/create/` links (lines ~1089, 1107) are fine
   for logged-in users (they're in the "Resources" / "Quick Links" sections).
   Optionally wrap them in auth checks too, but lower priority.

4. **Dropdown menu links** (lines 179, 196) — These are inside navigation and
   labelled "Tab Room" / "IE Suite". Leave as-is since they're secondary paths.

5. **Do NOT change** the `{% url 'register-organization' %}` hero CTA — it
   already goes to the Phase 7 registration flow.

6. **Add returning-user nudge** below the hero CTAs:
   ```html
   {% if not user.is_authenticated %}
     <p class="em-hero-login-hint">
       Already have an account?
       <a href="{% url 'login' %}" style="color: rgba(255,255,255,0.9); text-decoration: underline;">Sign in</a>
     </p>
   {% endif %}
   ```
   Add matching CSS in `landing.css`:
   ```css
   .em-hero-login-hint {
       margin-top: 1rem;
       font-size: 0.9rem;
       color: rgba(255, 255, 255, 0.7);
   }
   ```

---

### FIX 5 — I1: Rewrite homepage H1 with SEO keywords

**The problem:** The H1 "The operating system for debate" contains no searchable
keywords. Debate coaches search for "debate tabulation software" not "operating
system for debate."

**Current H1 (exact HTML):**
```html
<h1 id="hero-title" class="em-hero-title">
  The operating system<br><span class="em-gradient-text">for debate</span>
</h1>
```

**What to do:**

1. Rewrite the H1 to contain primary keywords while preserving the CSS classes:
   ```html
   <h1 id="hero-title" class="em-hero-title">
     Free debate tabulation<br><span class="em-gradient-text">for every format</span>
   </h1>
   ```
   This keeps the `em-hero-title` class and `em-gradient-text` gradient span.
   And it puts "free debate tabulation" (the #1 search term) in the H1.

   **Alternative (if the tagline feel is preferred):**
   ```html
   <h1 id="hero-title" class="em-hero-title">
     The tab software<br><span class="em-gradient-text">that's actually free</span>
   </h1>
   ```

2. Move the old tagline to a smaller element AFTER the H1:
   ```html
   <div class="em-badge" style="margin-top: 0.5rem;" aria-hidden="true">
     The operating system for debate
   </div>
   ```

3. Shorten the `<title>` tag from 74 chars to under 65:
   - Current: `NekoTab — Free Debate Tournament Tabulation Software | AI Motion Analysis` (74 chars)
   - New: `NekoTab — Free Debate Tabulation Software | BP, WSDC, Australs` (62 chars)

4. **Fix the FAQ contradiction.** The FAQ answer for "Is it free to use?" says:
   > "NekoTab is open-source and free to self-host. You can also use our hosted
   > service for a simple one-time fee."

   This CONTRADICTS the "free forever" messaging. Change to:
   ```html
   <p>Yes — NekoTab is completely free to use. Create an account, set up your
   tournament, and start tabbing. No hidden fees, no per-tournament charges.
   You can also self-host for full data sovereignty.</p>
   ```

5. **Also fix the JSON-LD `FAQPage` structured data** in the `<head>` — the
   same wrong text appears there. Update the "Is it free to use?" answer in
   the JSON-LD block to match the corrected FAQ answer above.

---

### FIX 6 — I2: Add Content-Security-Policy and Permissions-Policy

**The problem:** CSP and Permissions-Policy headers are missing. Django's
`SecurityMiddleware` already handles X-Frame-Options, X-Content-Type-Options,
HSTS, and Referrer-Policy — so DO NOT duplicate those in nginx.

**Nginx `add_header` inheritance warning:** If you add `add_header` directives
to the `server` block, they will NOT be inherited by any `location` block that
has its own `add_header`. The `/static/` block already has
`add_header Cache-Control "public"`, so server-level headers would be dropped
for static file requests. There are two approaches:

**Approach A (Recommended): Add CSP and Permissions-Policy in EVERY location block
that has its own `add_header`:**

For `config/nginx.conf.erb`, in the `server` block (applies to `/` and other
location blocks WITHOUT their own `add_header`):
```nginx
# Security headers (CSP + Permissions-Policy only — Django handles the rest)
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://pagead2.googlesyndication.com https://www.googletagmanager.com https://www.google-analytics.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' https://*.nekotab.app wss://*.nekotab.app https://www.google-analytics.com; frame-ancestors 'none';" always;
add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
```

**Why `'unsafe-inline'` and `'unsafe-eval'` are necessary:**
- `'unsafe-inline'` — Required because the homepage template has inline
  `<script>` blocks (AdSense, cookie consent, GA4 loading).
- `'unsafe-eval'` — Required because `vue.config.js` has `runtimeCompiler: true`,
  which uses `new Function()` / `eval()` to compile templates at runtime.
- DO NOT remove these without a full code audit — it will break functionality.

Then, in the `/static/` location block, also add CSP + Permissions-Policy
alongside the existing Cache-Control:
```nginx
location /static/ {
    alias /app/tabbycat/staticfiles/;
    access_log off;
    add_header Cache-Control "public";
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://pagead2.googlesyndication.com https://www.googletagmanager.com https://www.google-analytics.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' https://*.nekotab.app wss://*.nekotab.app https://www.google-analytics.com; frame-ancestors 'none';" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
    expires 7d;
    etag on;
}
```

**Approach B (Simpler, Django-only — no nginx changes for CSP):**

Add `SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'` in `core.py` and
use a custom middleware to set CSP. But this is more code. Approach A is simpler
for a first implementation.

**For `config/nginx-docker.conf`:** Apply the same CSP + Permissions-Policy
headers. The Docker `/static/` block also has its own `add_header`, so it needs
the security headers added there too.

**Also add HSTS preload to `core.py`:**
```python
SECURE_HSTS_PRELOAD = True
```
Then submit nekotab.app to https://hstspreload.org after deployment.

---

### FIX 7 — I3: Enable code splitting in vue.config.js

**The problem:** `config.optimization.splitChunks(false)` in `vue.config.js`
prevents all code splitting, even though `main.js` already has 20+ lazy-loaded
components using `() => import(...)` syntax.

**What to do:**

1. In `vue.config.js`, find:
   ```javascript
   // Don't split out vendors file
   chainWebpack: config => {
     config.optimization.splitChunks(false)
   },
   ```

2. Change to:
   ```javascript
   // Allow code splitting for lazy-loaded components
   chainWebpack: config => {
     config.optimization.splitChunks({
       chunks: 'async',  // Only split async (lazy) imports — keep main bundle intact
     })
   },
   ```

   Using `chunks: 'async'` (not `'all'`) means only the lazy-loaded components
   (Forum, Motion Bank, Passport, IE, Congress — the `() => import(...)` calls
   in `main.js`) get split into separate chunks. The core components that are
   statically imported stay in the main bundle. This is the safest change.

3. **Rebuild Vue locally and commit the output:**
   ```bash
   npx vue-cli-service build
   ```
   Verify: `ls tabbycat/static/vue/js/` should now show multiple `.js` files
   (e.g., `app.js`, `ForumHome.js`, `MotionBankHome.js`, etc.) instead of a
   single `app.js`.

4. **Commit the rebuilt files.** Heroku does NOT build Vue — it uses the
   pre-built files from git.

⚠️ **MANUAL STEP REQUIRED:** Must run `npx vue-cli-service build` locally before
committing. Verify chunk files exist in `tabbycat/static/vue/js/`.

---

### FIX 8 — I4: Add social proof section to homepage

**The problem:** No testimonials, no tournament count, no trust signals. The
"TRUSTED BY DEBATE COMMUNITIES WORLDWIDE" banner is generic emoji icons,
not real social proof.

**Critical:** The homepage uses custom `em-*` CSS classes (from `landing.css`),
NOT Bootstrap utility classes. All new HTML must follow the homepage's design
language.

**What to do:**

1. In `nekotab_home.html`, find the hero section closing (`</section>` for
   `em-hero`) and add a social proof strip IMMEDIATELY AFTER:

```html
<!-- Social proof strip -->
<section class="em-section em-social-proof" aria-label="Platform statistics">
  <div class="em-container">
    <div class="em-proof-grid">
      <div class="em-proof-stat">
        <span class="em-proof-number">40+</span>
        <span class="em-proof-label">Tournaments tabulated</span>
      </div>
      <div class="em-proof-stat">
        <span class="em-proof-number">20+</span>
        <span class="em-proof-label">Countries</span>
      </div>
      <div class="em-proof-stat">
        <span class="em-proof-number">$0</span>
        <span class="em-proof-label">Cost, forever</span>
      </div>
      <div class="em-proof-stat">
        <span class="em-proof-number">BP · WSDC · Australs</span>
        <span class="em-proof-label">All major formats</span>
      </div>
    </div>

    <!-- TODO: Testimonials — collect real quotes from tournament directors.
         Contact 3 directors who have used NekoTab and ask for a 2-sentence quote.
         Template for when quotes are collected:
         <div class="em-testimonial">
           <blockquote>"[Exact quote from director]"</blockquote>
           <cite>— [Name], [Role], [University/Tournament]</cite>
         </div>
         DO NOT fabricate testimonials.
    -->
  </div>
</section>
```

2. Add CSS to `tabbycat/static/css/landing.css`:

```css
/* ── Social Proof Strip ── */
.em-social-proof {
    padding: 2.5rem 0;
    border-top: 1px solid var(--border-primary);
    border-bottom: 1px solid var(--border-primary);
    background: var(--surface-alt);
}

.em-proof-grid {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 3rem;
    flex-wrap: wrap;
}

.em-proof-stat {
    text-align: center;
    padding: 0 1.5rem;
}

.em-proof-stat:not(:last-child) {
    border-right: 1px solid var(--border-primary);
}

.em-proof-number {
    display: block;
    font-size: 1.75rem;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.2;
}

.em-proof-label {
    display: block;
    font-size: 0.8rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 0.25rem;
}

@media (max-width: 640px) {
    .em-proof-grid {
        gap: 1.5rem;
    }
    .em-proof-stat {
        padding: 0 0.75rem;
    }
    .em-proof-stat:not(:last-child) {
        border-right: none;
    }
}
```

Note: Uses CSS custom properties (`--border-primary`, `--surface-alt`, etc.)
that are already defined in landing.css's `:root` block.

---

### FIX 9 — I5: Fix /api/ returning HTTP 500

**The problem:** `GET https://nekotab.app/api/` returns HTTP 500.

**Root cause investigation:** The API root view exists — `APIRootView` in
`tabbycat/api/views.py` inherits from `PublicAPIMixin, GenericAPIView` and
returns a response with `_links`, `timezone`, `version`, `version_name`. It
references `serializers.RootSerializer`. The 500 is likely a serializer import
error or a missing DRF renderer configuration.

**What to do:**

1. Read `tabbycat/api/views.py` — find `APIRootView` and `RootSerializer`.
2. Read `tabbycat/api/serializers.py` — find `RootSerializer` and check if
   it's properly defined.
3. The most likely cause: `RootSerializer` may reference a model or field that
   doesn't exist, OR the DRF browsable API renderer tries to render HTML but
   fails because it's disabled in `REST_FRAMEWORK['DEFAULT_RENDERER_CLASSES']`
   (only `JSONRenderer` is enabled, no `BrowsableAPIRenderer`).

   **If the issue is the renderer:** A browser `GET /api/` sends
   `Accept: text/html` which DRF can't satisfy with only `JSONRenderer`.
   Fix by ensuring `APIRootView` explicitly returns JSON:
   ```python
   from rest_framework.renderers import JSONRenderer

   class APIRootView(PublicAPIMixin, GenericAPIView):
       renderer_classes = [JSONRenderer]
       # ...
   ```

4. **If the issue is the serializer:** Fix the `RootSerializer` or simplify
   `APIRootView` to not use a serializer:
   ```python
   class APIRootView(PublicAPIMixin, GenericAPIView):
       def get(self, request, format=None):
           return Response({
               "_links": {"v1": reverse('api-v1-root', request=request, format=format)},
               "timezone": settings.TIME_ZONE,
               "version": settings.TABBYCAT_VERSION,
           })
   ```

5. **Test locally** before committing:
   ```bash
   curl -H "Accept: application/json" http://localhost:8000/api
   ```
   It should return 200 with the JSON body above.

**Note:** The main urls.py registers this as `path('api', include('api.urls'))` —
no trailing slash. DRF's `APPEND_SLASH` setting and Django's `CommonMiddleware`
may affect whether `/api` vs `/api/` works. Check both.

---

### FIX 10 — I6: Add "Powered by NekoTab" conversion CTA to tournament pages

**The problem:** Public tournament result pages (viewed by hundreds of coaches
and students) lack a conversion-oriented NekoTab CTA. The existing footer says
"NekoTab is an open-source project" but doesn't drive signup.

**What to do:**

1. Edit `tabbycat/templates/footer.html` — the template used by ALL pages that
   extend `base.html` (including tournament results, draw, standings, etc.).

2. Add a conversion line BEFORE the existing footer content, visible only on
   public pages (not admin/assistant):
   ```html
   {% if not user_is_admin %}
   <div class="text-center py-2 small" style="border-bottom: 1px solid rgba(0,0,0,.08);">
       Tabulated with
       <a href="https://nekotab.app" target="_blank" rel="noopener" style="font-weight: 600;">NekoTab</a>
       — free debate tabulation software.
       <a href="https://nekotab.app/register/tournament/" target="_blank" rel="noopener" class="ml-2" style="font-weight: 600;">
           Run your next tournament free →
       </a>
   </div>
   {% endif %}
   ```

3. **Verify coverage.** Since `base.html` includes `footer.html` and ALL
   tournament pages extend `base.html`, this single change covers:
   - `/<slug>/` — tournament public index
   - `/<slug>/results/` — results page
   - `/<slug>/draw/` — public draw
   - `/<slug>/speakers/` — speaker standings
   - `/<slug>/teams/` — team standings
   - `/<slug>/break/` — break announcements

4. **Check the context variable:** The template uses `user_is_admin` — verify
   this variable exists in the template context. Search for it in views or
   context processors. If it doesn't exist, use an alternative like:
   ```html
   {% if not request.path|slice:":6" == "/admin" %}
   ```
   Or check for a different context variable that indicates admin vs public.

---

### FIX 11 — I7: Update meta descriptions and fix FAQ inconsistency

**The problem:** The FAQ and JSON-LD structured data claim NekoTab charges a
"simple one-time fee" for hosting — contradicting the "free" messaging. The
meta description is reasonable but can be improved.

**What to do:**

1. **Homepage `<meta name="description">`** — current content (~168 chars):
   > "NekoTab is the #1 open-source debate tournament platform. Run British
   > Parliamentary, Australs & WSDC tournaments with automated draws, digital
   > ballots, AI motion analysis, and real-time results. Free to use."

   Update to be more conversion-focused (under 160 chars):
   ```html
   <meta name="description" content="Free debate tabulation software for BP, WSDC, Australs and more. Automated draws, digital ballots, live standings, AI motion analysis. Trusted by 40+ tournaments worldwide.">
   ```
   (159 characters)

2. **Fix the FAQ `<details>` answer** for "Is it free to use?" (line ~1003):
   Current: `"NekoTab is open-source and free to self-host. You can also use our hosted service for a simple one-time fee."`
   New: `"Yes — NekoTab is completely free to use. No per-tournament fees, no hidden charges. Create an account and start tabbing immediately. You can also self-host for full data sovereignty."`

3. **Fix the JSON-LD `FAQPage` data** in the `<head>` — find the same question
   in the structured data block and update the answer text to match.

4. **Update Open Graph description** to match the new meta description:
   ```html
   <meta property="og:description" content="Free debate tabulation software for BP, WSDC, Australs and more. Automated draws, digital ballots, live standings, AI motion analysis." />
   ```

---

### FIX 12 — G2: Homepage "free" messaging prominence + competitor comparison

**The problem:** "Free" is not in the hero headline, not in the CTA text,
and doesn't appear prominently until the FAQ. The hero badge already says
"Open-source · Free to self-host" but it's small and uses technical language.

**What to do:**

1. **Update the hero badge** (line ~217):
   Current: `Open-source &middot; Free to self-host`
   New: `100% Free &middot; Open-source &middot; No setup required`

2. **The H1 change from Fix 5** already adds "Free" to the headline.

3. **The CTA change from Fix 4** already adds "Free" to button text.

4. **Add a competitor comparison strip** after the social proof section (Fix 8).
   Place it between the social proof and the "Platform" section:

```html
<!-- Competitor comparison -->
<section class="em-section em-comparison" aria-label="How NekoTab compares">
  <div class="em-container" style="text-align: center;">
    <p class="em-comparison-label">How NekoTab compares</p>
    <div class="em-comparison-pills">
      <span class="em-pill">✓ Free forever <small>(vs Calico $40/tournament)</small></span>
      <span class="em-pill">✓ No NSDA lock-in <small>(vs Tabroom)</small></span>
      <span class="em-pill">✓ No server setup <small>(vs self-hosted Tabbycat)</small></span>
      <span class="em-pill">✓ BP + WSDC + Australs</span>
    </div>
  </div>
</section>
```

5. Add CSS to `landing.css`:
```css
/* ── Competitor Comparison ── */
.em-comparison {
    padding: 1.5rem 0;
    background: var(--surface-primary);
}

.em-comparison-label {
    font-size: 0.8rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.75rem;
}

.em-comparison-pills {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: 0.75rem;
}

.em-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.5rem 1rem;
    background: var(--surface-alt);
    border: 1px solid var(--border-primary);
    border-radius: var(--radius-full, 100px);
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--text-primary);
}

.em-pill small {
    color: var(--text-muted);
    font-weight: 400;
}
```

---

### FIX 13 — G1: SEO content page stubs + sitemap additions

**The problem:** NekoTab has no long-tail SEO content. Targeted pages for
"free debate tab software" or "BP debate tabulation" would capture high-intent
search traffic from coaches actively looking for tools.

**What to do:**

1. **Do NOT re-create `TournamentSitemap`** — it already exists in
   `tabbycat/sitemaps.py`. Verify it includes `active=True, is_listed=True`
   tournaments (it does).

2. **Add the registration and marketing pages** to the sitemap. In
   `tabbycat/sitemaps.py`, update `StaticViewSitemap`:

```python
class StaticViewSitemap(Sitemap):
    changefreq = "weekly"

    _priorities = {
        'tabbycat-index': 1.0,
        'motionbank:motion-doctor': 0.9,
        'motionbank:motionbank-home': 0.9,
        'forum:forum-home': 0.7,
        'passport:passport-directory': 0.6,
        'seo-free-tab': 0.9,
        'seo-bp-tab': 0.9,
        'seo-tabroom-alt': 0.9,
    }

    def items(self):
        return [
            'tabbycat-index',
            'forum:forum-home',
            'motionbank:motionbank-home',
            'motionbank:motion-doctor',
            'passport:passport-directory',
            'seo-free-tab',
            'seo-bp-tab',
            'seo-tabroom-alt',
        ]

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        return self._priorities.get(item, 0.7)
```

3. **Create SEO page templates.** Create directory `tabbycat/templates/pages/`
   and add three template files:

**Template 1:** `tabbycat/templates/pages/free-debate-tab-software.html`
```html
{% extends "base.html" %}
{% load i18n %}

{% block page-title %}Free Debate Tabulation Software{% endblock %}
{% block head-title %}<span class="emoji">🎯</span> Free Debate Tab Software{% endblock %}

{% block sub-title %}
<meta name="description" content="NekoTab is free debate tabulation software supporting BP, WSDC, Australs and more. Automated draws, digital ballots, live standings. No fees, no setup.">
<link rel="canonical" href="https://nekotab.app/free-debate-tab-software/" />
{% endblock %}

{% block content %}
<div class="container mt-4">
  <div class="row">
    <div class="col-lg-8 mx-auto">
      <h1>Free Debate Tabulation Software for Every Format</h1>

      <p class="lead">NekoTab is a completely free, open-source debate tournament
      management platform. Run BP, WSDC, Australs, and other parliamentary debate
      tournaments with automated draws, digital ballot entry, real-time standings,
      and break calculations — all from your browser.</p>

      <h2>Why NekoTab Is Free</h2>
      <p>Unlike Calico ($40 per tournament) or self-hosted Tabbycat (which
      requires technical setup and ongoing hosting costs), NekoTab is hosted
      for you at no charge. Create an account, set up your tournament, and
      start tabbing in under 3 minutes.</p>

      <!-- TODO: Expand with 500+ words of genuine, helpful content:
           - Detailed feature list with screenshots
           - Step-by-step "how it works" section
           - Format support details (BP 4-team, Australs 3v3, WSDC reply speeches)
           - Comparison table: NekoTab vs Calico vs Tabroom vs self-hosted
           - FAQ section specific to pricing/cost questions
           - CTAs linking to /register/tournament/
      -->

      <div class="mt-4">
        <a href="{% url 'register-tournament' %}" class="btn btn-primary btn-lg">
          Create Your First Tournament — Free
        </a>
      </div>
    </div>
  </div>
</div>
{% endblock %}
```

**Template 2:** `tabbycat/templates/pages/bp-debate-tabulation.html`
```html
{% extends "base.html" %}
{% load i18n %}

{% block page-title %}British Parliamentary Debate Tabulation{% endblock %}
{% block head-title %}<span class="emoji">🇬🇧</span> BP Debate Tab{% endblock %}

{% block sub-title %}
<meta name="description" content="Free British Parliamentary debate tabulation with NekoTab. 4-team BP draws, power-pairing, side balancing, digital ballots, live standings. No fees.">
<link rel="canonical" href="https://nekotab.app/bp-debate-tabulation/" />
{% endblock %}

{% block content %}
<div class="container mt-4">
  <div class="row">
    <div class="col-lg-8 mx-auto">
      <h1>British Parliamentary Debate Tabulation — Free & Hosted</h1>

      <p class="lead">NekoTab provides full support for the British Parliamentary
      (BP) format with 4-team draws, power-pairing, side balancing, pull-ups,
      and swing teams — all generated automatically.</p>

      <!-- TODO: Expand with detailed BP-specific content:
           - How BP draws work in NekoTab
           - Power-pairing algorithm explanation
           - Side balance and constraint configuration
           - Speaker tab and team tab calculation
           - Break eligibility rules
           - Step-by-step guide for a first-time BP tournament director
      -->

      <div class="mt-4">
        <a href="{% url 'register-tournament' %}" class="btn btn-primary btn-lg">
          Create a BP Tournament — Free
        </a>
      </div>
    </div>
  </div>
</div>
{% endblock %}
```

**Template 3:** `tabbycat/templates/pages/tabroom-alternative.html`
```html
{% extends "base.html" %}
{% load i18n %}

{% block page-title %}Free Tabroom Alternative{% endblock %}
{% block head-title %}<span class="emoji">🌐</span> Tabroom Alternative{% endblock %}

{% block sub-title %}
<meta name="description" content="Looking for a free Tabroom alternative? NekoTab supports BP, WSDC, Australs and international debate formats. No NSDA membership required.">
<link rel="canonical" href="https://nekotab.app/tabroom-alternative/" />
{% endblock %}

{% block content %}
<div class="container mt-4">
  <div class="row">
    <div class="col-lg-8 mx-auto">
      <h1>A Free, International Alternative to Tabroom</h1>

      <p class="lead">Tabroom is built for the US forensics ecosystem and
      requires NSDA membership. If you run international parliamentary debate
      tournaments (BP, WSDC, Australs), NekoTab is a free, modern alternative
      with purpose-built features.</p>

      <!-- TODO: Expand with comparison content:
           - NekoTab vs Tabroom feature comparison table
           - Format support differences (BP, WSDC, Australs vs US formats)
           - Why international debate coaches prefer NekoTab
           - Migration guide: moving from Tabroom to NekoTab
      -->

      <div class="mt-4">
        <a href="{% url 'register-tournament' %}" class="btn btn-primary btn-lg">
          Try NekoTab Free
        </a>
      </div>
    </div>
  </div>
</div>
{% endblock %}
```

4. **Add URL patterns** in `tabbycat/urls.py`. Place them BEFORE the
   `<slug:tournament_slug>` catch-all pattern:

```python
from django.views.generic import TemplateView

# SEO landing pages (before tournament slug catch-all)
path('free-debate-tab-software/', TemplateView.as_view(
    template_name='pages/free-debate-tab-software.html'
), name='seo-free-tab'),
path('bp-debate-tabulation/', TemplateView.as_view(
    template_name='pages/bp-debate-tabulation.html'
), name='seo-bp-tab'),
path('tabroom-alternative/', TemplateView.as_view(
    template_name='pages/tabroom-alternative.html'
), name='seo-tabroom-alt'),
```

5. **Update `robots.txt`** — the SEO pages must be allowed. Check that none of
   the `Disallow` patterns accidentally block them. They should be fine since
   they're not under any blocked prefix.

---

## AFTER ALL 13 FIXES

### Step 1 — Install new dependency
```bash
pipenv install django-axes
# OR: pip install django-axes
```

### Step 2 — Run migrations
```bash
python manage.py migrate
```
This applies: axes tables + site domain fix.

### Step 3 — Rebuild Vue bundle (Fix 7 changed vue.config.js)
```bash
npx vue-cli-service build
```
Verify: multiple chunk files in `tabbycat/static/vue/js/` instead of a single
`app.js`.

### Step 4 — Run collectstatic (after Vue rebuild)
```bash
python manage.py collectstatic --noinput
```

### Step 5 — Verify sitemap locally
```bash
python manage.py runserver
curl http://localhost:8000/sitemap.xml | head -20
```
Every `<loc>` must say `https://nekotab.app/...` (not `example.com`).

### Step 6 — Commit everything
```bash
git add -A
git commit -m "fix: audit remediation — 13 issues resolved

Critical:
- Fix sitemap domain (example.com → nekotab.app) via data migration
- Remove static directory listing (autoindex off in nginx)
- Add brute-force protection (django-axes)
- Fix homepage CTAs for unauthenticated users

Important:
- Rewrite H1 with SEO keywords + fix FAQ pricing contradiction
- Add CSP and Permissions-Policy headers
- Enable Vue code splitting (remove splitChunks(false))
- Add social proof section to homepage
- Fix /api/ 500 error
- Add 'Powered by NekoTab' CTA to tournament footers
- Update meta descriptions and OG tags

Growth:
- Add competitor comparison strip
- Create 3 SEO landing page stubs + register in sitemap"
```

### Step 7 — Deploy
```bash
git push origin main
```

### Step 8 — Post-deploy production steps
```bash
heroku run python manage.py migrate --app <MAIN-APP>
```

### Step 9 — Verify production
```bash
# Sitemap domain correct
curl https://nekotab.app/sitemap.xml | head -20

# Directory listing removed
curl -I https://nekotab.app/static/
# Should return 403, not a directory listing

# Security headers present
curl -I https://nekotab.app
# Should include Content-Security-Policy and Permissions-Policy

# API root no longer 500
curl https://nekotab.app/api
# Should return 200 JSON

# SEO pages accessible
curl -I https://nekotab.app/free-debate-tab-software/
# Should return 200
```

### Step 10 — Submit sitemap to Google Search Console
Go to: https://search.google.com/search-console
Add property: nekotab.app (if not already added)
Submit sitemap: https://nekotab.app/sitemap.xml
⚠️ **This is a manual browser step — remind the developer.**

---

## HARD CONSTRAINTS

1. **Read every file before changing it.** If you haven't read a file, you
   cannot make assumptions about its content.

2. **Show every changed section with 10 lines of context before and after.**
   For 2000-line files like `nekotab_home.html`, showing the complete file is
   impractical. Show just the changed sections with enough context to be
   unambiguous.

3. **Do not break any existing functionality.** Test each change mentally:
   - Fix 2 (autoindex off): static files still serve? Yes — autoindex only
     affects directory browsing, not file serving.
   - Fix 3 (django-axes): existing login still works? Yes — axes hooks into
     the auth backend, doesn't replace it. TournamentAdminBackend still runs.
   - Fix 7 (code splitting): existing components still load? Yes — main.js
     already has lazy imports. We're just un-blocking them.
   - Fix 6 (CSP): existing inline scripts still work? Yes — `'unsafe-inline'`
     is included. Vue runtime compiler works? Yes — `'unsafe-eval'` is included.

4. **Mark any fix that requires a manual production step** with:
   `⚠️ MANUAL STEP REQUIRED AFTER DEPLOY: [exact command]`

5. **Do not fabricate testimonials** for Fix 8. Leave a clearly marked TODO
   with instructions on how to collect real quotes.

6. **The sitemap fix (Fix 1) MUST be a data migration**, not a shell command.
   Shell commands on Heroku don't run automatically on redeploy.

7. **Use the homepage's `em-*` CSS classes** for any HTML added to
   `nekotab_home.html`. Do NOT use Bootstrap utility classes on the homepage.

8. **The nginx `add_header` inheritance rule is non-negotiable.** Any location
   block with its own `add_header` does NOT inherit server-level `add_header`.
   If you add security headers at the server level, you MUST also add them to
   the `/static/` location block (which already has `add_header Cache-Control`).

---

## OUTPUT FORMAT

For each fix:
```
--- Fix N: [name] ---
Files read: [list]
Issue confirmed: [yes/no — what you found]
Files changed: [list]
[Changed sections with 10 lines of context before and after]
Manual step required: [yes/no — if yes, exact command]
Fix N complete.
```

After all 13 fixes:
```
=== Summary ===
Files changed: [complete list]
Migrations created: [list]
Manual steps after deploy: [numbered list]
npm run build required: [yes/no]
```

Start with reading all files. State file count before beginning Fix 1.
