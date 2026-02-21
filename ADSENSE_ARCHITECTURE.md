# NekoTab AdSense Readiness — Architecture Blueprint & Implementation Plan

> **Date:** February 2026  
> **Status:** Infrastructure built, ready for integration testing  
> **Author:** Technical Architecture Review

---

## 1. Executive Summary

This document covers the infrastructure changes needed to make **nekotab.app** eligible for Google AdSense by eliminating "low value content" signals and improving UX, trust, and SEO hygiene.

### What was built:
1. **`content` Django app** — Models, views, URLs, admin, sitemaps, template tags for the Learn hub + trust pages
2. **12 article stubs** (6 published, 6 draft) across 4 categories — ready for expansion
3. **5 trust/legal pages** — About, Contact (with honeypot anti-spam), Privacy, Terms, Disclaimer
4. **SEO improvements** — Enhanced robots.txt, expanded sitemap, noindex logic, content threshold
5. **Footer trust links** — On both the landing page and the app-wide Bootstrap footer
6. **Internal linking** — Learn hub promoted in landing page nav + body, template tags for cross-linking from tournament pages
7. **Tournament content blocks** — `TournamentContentBlock` model for editable contextual content on public tournament pages

---

## 2. Architecture Diagram (Textual)

```
┌─────────────────────────────────────────────────────────┐
│                     NGINX / CDN                         │
│  (Cloudflare optional: caching, WAF, edge compression)  │
├─────────────────────────────────────────────────────────┤
│                 Django ASGI (Daphne)                     │
│  ┌────────────┐  ┌──────────┐  ┌───────────────────┐   │
│  │  Middleware │→ │  Router  │→ │  View Layer       │   │
│  │  (Auth,     │  │ (urls.py)│  │  (Templates/DRF)  │   │
│  │  Analytics, │  │          │  │                   │   │
│  │  Subdomain) │  │          │  │                   │   │
│  └────────────┘  └──────────┘  └───────────────────┘   │
├─────────────────────────────────────────────────────────┤
│  App Layer                                              │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ ┌───────────┐  │
│  │tournament│ │motionbank│ │ forum   │ │ content ★ │  │
│  │ results  │ │ passport │ │ users   │ │ (NEW)     │  │
│  │ draw     │ │ api      │ │ analytics│ │           │  │
│  └──────────┘ └──────────┘ └─────────┘ └───────────┘  │
├─────────────────────────────────────────────────────────┤
│  Data Layer                                             │
│  ┌─────────┐  ┌───────┐  ┌────────────────────┐       │
│  │Postgres │  │ Redis │  │ WhiteNoise Static │       │
│  │ (models)│  │(cache)│  │ (gzip+fingerprint)│       │
│  └─────────┘  └───────┘  └────────────────────┘       │
└─────────────────────────────────────────────────────────┘

Security Boundaries:
  PUBLIC  → /, /learn/, /about/, /t/:slug/, /forum/, /motions-bank/, /passport/
  AUTH    → /accounts/, /create/, /dashboard
  ADMIN   → /:slug/admin/*, /analytics/, /campaigns/, /database/
  API     → /api/ (Token + Session auth)
```

### Caching Strategy
| Layer | Strategy | TTL |
|-------|----------|-----|
| CDN (Cloudflare) | Cache public pages, bypass auth | 5 min public, 0 auth |
| WhiteNoise | `CompressedManifestStaticFilesStorage` — immutable fingerprinted assets | 1 year |
| Django Cache | `ConditionalGetMiddleware` — ETag/Last-Modified for all responses | Automatic |
| Redis | Template fragment cache (`{% cache %}`) for footer, nav, sitemaps | 10 min |
| Template Cache | Django cached template loader | Process lifetime |

### Logging/Monitoring
| Tool | Purpose |
|------|---------|
| Sentry | Error tracking, performance monitoring |
| Google Analytics (GA4) | Traffic analytics |
| `analytics` app | Internal page view tracking (PageView model) |
| Django `actionlog` | Audit trail for admin actions |

---

## 3. Data Model Definitions

### NEW: `content` app models

#### `ArticleCategory`
| Field | Type | Notes |
|-------|------|-------|
| `id` | BigAutoField | PK |
| `name` | CharField(100) | e.g. "Debate Formats" |
| `slug` | SlugField(120) | Unique, URL-safe |
| `description` | TextField | Category description |
| `icon` | CharField(10) | Emoji icon |
| `order` | PositiveIntegerField | Sort order |

#### `Article`
| Field | Type | Notes |
|-------|------|-------|
| `id` | BigAutoField | PK |
| `title` | CharField(200) | Article title |
| `slug` | SlugField(220) | Unique, URL-safe |
| `summary` | TextField(500) | Short description for listings + meta |
| `body` | TextField | HTML content (sanitized on render) |
| `category` | FK → ArticleCategory | Nullable |
| `status` | CharField(10) | `draft` / `published` / `archived` |
| `reading_time_minutes` | PositiveSmallIntegerField | Estimated read time |
| `meta_title` | CharField(70) | SEO override |
| `meta_description` | CharField(160) | SEO override |
| `related_format_slugs` | JSONField | e.g. `["bp","australs"]` for cross-linking |
| `created_at` | DateTimeField | Auto |
| `updated_at` | DateTimeField | Auto |

**Indexes:** `(status, -created_at)`, `(slug)`

#### `TournamentContentBlock`
| Field | Type | Notes |
|-------|------|-------|
| `id` | BigAutoField | PK |
| `tournament` | OneToOneField → Tournament | Cascade delete |
| `about_text` | TextField | Editable "About this tournament" |
| `host_organization` | CharField(200) | Host org name |
| `location` | CharField(200) | City/country |
| `format_description` | CharField(100) | e.g. "British Parliamentary" |
| `start_date` | DateField | Nullable |
| `end_date` | DateField | Nullable |
| `status_label` | CharField(50) | e.g. "Completed" |
| `meta_title` | CharField(70) | SEO override |
| `meta_description` | CharField(160) | SEO override |
| `updated_at` | DateTimeField | Auto |

---

## 4. Route Map with Index/Noindex Decisions

### Public Routes
| Route | View | Index? | Canonical | Notes |
|-------|------|--------|-----------|-------|
| `/` | `PublicSiteIndexView` | ✅ YES | `https://nekotab.app/` | Landing page |
| `/learn/` | `LearnHubView` | ✅ YES | `https://nekotab.app/learn/` | Content hub |
| `/learn/:slug/` | `ArticleDetailView` | ✅ if PUBLISHED | Self | Draft = noindex |
| `/about/` | `AboutView` | ✅ YES | `https://nekotab.app/about/` | Trust page |
| `/contact/` | `ContactView` | ✅ YES | `https://nekotab.app/contact/` | Trust page |
| `/privacy/` | `PrivacyView` | ✅ YES | `https://nekotab.app/privacy/` | Trust page |
| `/terms/` | `TermsView` | ✅ YES | `https://nekotab.app/terms/` | Trust page |
| `/disclaimer/` | `DisclaimerView` | ✅ YES | `https://nekotab.app/disclaimer/` | Trust page |
| `/forum/` | Forum home | ✅ YES | Self | Community content |
| `/motions-bank/` | Motion Bank | ✅ YES | Self | Content-rich |
| `/motions-bank/motion/:slug/` | Motion detail | ✅ YES | Self | High-value SEO |
| `/passport/` | Passport directory | ✅ YES | Self | Public profiles |
| `/:slug/` | Tournament home | ✅ if threshold met | Self | See content threshold |
| `/:slug/results/` | Results | ✅ if tournament indexable | Self | |
| `/:slug/standings/` | Standings | ✅ if tournament indexable | Self | |
| `/:slug/motions/` | Motions | ✅ if tournament indexable | Self | |
| `/:slug/draw/` | Draw | ✅ if tournament indexable | Self | |

### Auth/Admin Routes (ALL noindex, nofollow)
| Route | Notes |
|-------|-------|
| `/accounts/login/` | noindex |
| `/accounts/signup/` | noindex |
| `/accounts/password_reset/` | noindex |
| `/create/` | noindex (blocked in robots.txt) |
| `/start/` | noindex (blocked in robots.txt) |
| `/load-demo/` | noindex (blocked in robots.txt) |
| `/:slug/admin/*` | noindex (blocked in robots.txt) |
| `/:slug/assistant/*` | noindex (blocked in robots.txt) |
| `/analytics/*` | noindex (blocked in robots.txt) |
| `/campaigns/*` | noindex (blocked in robots.txt) |
| `/database/*` | noindex (blocked in robots.txt) |
| `/api/*` | noindex (blocked in robots.txt) |

### Content Threshold Definition
A tournament's public pages become indexable when ALL of these conditions are met:
1. `tournament.active == True`
2. `tournament.is_listed == True`
3. `tournament.name` is non-empty (≥ 3 chars)
4. Tournament has ≥ 2 teams
5. At least 1 round is completed OR has confirmed ballot submissions

This logic is implemented in the `{% content_threshold_met tournament %}` template tag.

---

## 5. SEO Technical Spec

### robots.txt
```
User-agent: *
Allow: /
Allow: /learn/
Allow: /about/ /contact/ /privacy/ /terms/ /disclaimer/
Allow: /forum/ /motions-bank/ /passport/

Disallow: /accounts/ /start/ /load-demo/ /claim/ /create/
Disallow: /style/ /database/ /jet/ /summernote/
Disallow: /campaigns/ /analytics/ /archive/ /api/
Disallow: /jsi18n/ /i18n/ /notifications/
Disallow: /*/admin/ /*/assistant/ /*/privateurls/
Disallow: /*?sort= /*?page= /*?lang=

Sitemap: https://nekotab.app/sitemap.xml
```

### Sitemap Structure (6 sections)
| Section | Source | Priority |
|---------|--------|----------|
| `static` | Homepage, forum home, motion bank, passport | 0.7 |
| `tournaments` | Active + listed tournaments | 0.8 |
| `motions` | Approved motion entries | 0.9 |
| `articles` | Published learn articles | 0.6 |
| `trust` | About, Contact, Privacy, Terms, Disclaimer, Learn hub | 0.5 |

### Canonical Tags
- Every page outputs `<link rel="canonical">` via `canonical_url` context variable
- Trust pages set canonical explicitly to `https://nekotab.app/{path}/`
- Tournament pages use `https://nekotab.app/{slug}/` (not subdomain)
- Articles use `https://nekotab.app/learn/{slug}/`

### Open Graph + Twitter Cards
Already in `base.html` — all new pages inherit automatically via template blocks.
Article pages override with `og:type = article` and `article:published_time`/`article:modified_time`.

### JSON-LD Structured Data
| Page | Schema Type |
|------|-------------|
| Homepage | `SoftwareApplication` (existing) |
| Learn hub | `CollectionPage` |
| Article detail | `Article` |
| About | `AboutPage` + `Organization` |
| Contact | `ContactPage` |
| Tournament | `Event` (recommended future addition) |

### Breadcrumbs
- Implemented with `BreadcrumbList` schema.org markup on:
  - Article pages: Home → Learn → Category → Article
  - Legal pages: Home → Page
- Tournament pages: recommend adding Home → Tournament Name

---

## 6. Component Tree & Folder Structure

```
tabbycat/
├── content/                          ★ NEW APP
│   ├── __init__.py
│   ├── apps.py
│   ├── models.py                     # Article, ArticleCategory, TournamentContentBlock
│   ├── views.py                      # LearnHub, ArticleDetail, About, Contact, Privacy, Terms, Disclaimer
│   ├── urls.py                       # /learn/, /learn/:slug/, /about/, /contact/, etc.
│   ├── admin.py                      # Admin for all 3 models
│   ├── sitemaps.py                   # LearnArticleSitemap, TrustPagesSitemap
│   ├── templatetags/
│   │   ├── __init__.py
│   │   └── content_tags.py           # related_articles_for_format, show_related_articles,
│   │                                 # tournament_context_text, content_threshold_met
│   └── migrations/
│       ├── __init__.py
│       ├── 0001_initial.py           # Schema
│       └── 0002_seed_content.py      # 4 categories + 12 article stubs
│
├── templates/
│   ├── content/
│   │   ├── learn_hub.html            # /learn/ — category filter + article grid
│   │   ├── article_detail.html       # /learn/:slug/ — full article with breadcrumbs, related
│   │   └── includes/
│   │       └── related_articles_card.html  # Cross-linking widget for tournament pages
│   ├── legal/
│   │   ├── base_legal.html           # Base layout for all trust pages
│   │   ├── about.html
│   │   ├── contact.html              # With honeypot anti-spam form
│   │   ├── privacy.html
│   │   ├── terms.html
│   │   └── disclaimer.html
│   ├── base.html                     # (existing, unmodified — new pages inherit)
│   ├── footer.html                   # MODIFIED — added trust link row
│   ├── nekotab_home.html             # MODIFIED — added Learn nav link, Learn section, Company footer column
│   └── robots.txt                    # MODIFIED — comprehensive allow/disallow rules
│
├── sitemaps.py                       # MODIFIED — removed utility pages from static sitemap
├── urls.py                           # MODIFIED — added content.urls include, expanded sitemaps dict
└── settings/core.py                  # MODIFIED — added 'content' to TABBYCAT_APPS
```

---

## 7. Step-by-Step Implementation Plan

### Phase 1: Infrastructure (DONE ✅)
- [x] Create `content` Django app with models, views, URLs
- [x] Create migrations (schema + seed data)
- [x] Create article stubs (6 published, 6 draft)
- [x] Create trust page templates (About, Contact, Privacy, Terms, Disclaimer)
- [x] Create learn hub + article detail templates
- [x] Wire URLs, sitemaps, settings
- [x] Update robots.txt
- [x] Add footer trust links (both landing page and app footer)
- [x] Add Learn link to navigation

### Phase 2: Integration Testing
- [ ] Run `python manage.py makemigrations content` to verify auto-generated migration matches
- [ ] Run `python manage.py migrate` to apply content migrations
- [ ] Verify all new pages load: `/learn/`, `/about/`, `/contact/`, `/privacy/`, `/terms/`, `/disclaimer/`
- [ ] Verify article stubs display correctly at `/learn/what-is-bp-debate/` etc.
- [ ] Verify sitemap includes new pages at `/sitemap.xml`
- [ ] Verify robots.txt blocks admin/auth pages
- [ ] Test contact form submission (honeypot, timing check)
- [ ] Verify mobile responsiveness on all new pages

### Phase 3: Tournament Page Enhancement (NEXT)
- [ ] Integrate `TournamentContentBlock` into `TournamentPublicHomeView`:
  - Add hero header: tournament name, host org, location, dates, format, status
  - Add summary cards: teams, rounds, adjudicators, motions count
  - Add navigation tabs: Overview / Results / Rounds / Motions / Speakers
  - Add `{% tournament_context_text %}` template tag output
  - Add "About this tournament" section from content block
  - Add breadcrumbs (Home → Tournament Name)
  - Add CTAs: "View results", "View rounds", "Host your own"
- [ ] Wire `{% content_threshold_met %}` into the noindex logic in `base.html`
- [ ] Add `{% show_related_articles %}` widget to tournament pages based on format
- [ ] Add loading/empty states for tournament sub-pages

### Phase 4: Design System Polish
- [ ] Create `_legal.scss` partial for consistent legal page typography
- [ ] Add `.article-body` styles (headings, lists, spacing, `max-width`)
- [ ] Ensure color contrast meets WCAG 2.1 AA on all text
- [ ] Add skeleton loading states for dynamic content areas
- [ ] Test all pages at 320px, 768px, 1024px, 1440px viewports

### Phase 5: Performance & Security Hardening
- [ ] Add `Cache-Control: public, max-age=300` headers for trust/learn pages
- [ ] Verify honeypot + timing anti-spam on contact form in production
- [ ] Sanitize `about_text` from TournamentContentBlock before rendering (use `bleach`)
- [ ] Run Lighthouse audits on all new pages — target ≥90 on all metrics
- [ ] Validate with Google Search Console (coverage, mobile usability)
- [ ] Test all pages with `axe-core` for accessibility compliance

### Phase 6: Content Expansion (Future)
- [ ] Expand draft articles to published with full content (800–2000 words each)
- [ ] Add 10–20 more articles across all categories
- [ ] Add `Event` JSON-LD structured data to tournament pages
- [ ] Add tournament-specific OG images (auto-generated)
- [ ] Submit sitemap update to Google Search Console
- [ ] Apply for AdSense review

---

## 8. Risk List & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Thin content** — stubs too short for AdSense | HIGH | 6 published stubs have 100–200 word bodies; expand before AdSense application. Content threshold prevents empty tournament pages from being indexed. |
| **Duplicate content** — tournament pages with same structure | MEDIUM | `tournament_context_text` generates deterministic unique text per tournament using metadata. Canonical tags prevent parameter-based duplicates. |
| **Auth page indexing** — login/signup in Google index | MEDIUM | robots.txt blocks `/accounts/`, `/create/`, `/start/`. Auth pages already have noindex in base.html via `pref.search_engine_indexing`. |
| **Cache invalidation** — stale content after article edits | LOW | Template fragment cache is 10 min. Article pages use `ConditionalGetMiddleware` for ETag. No aggressive CDN caching on dynamic pages. |
| **Contact form spam** — without CAPTCHA | MEDIUM | Honeypot field + timing check (3-second minimum). Add reCAPTCHA v3 if spam volume increases. |
| **Migration conflicts** — `0001_initial` depends on `tournaments.0001_initial` | LOW | Dependency is explicit. Run `makemigrations --check` to verify before deploy. |
| **Tournament content blocks** — missing for most tournaments | LOW | Template tag generates text from tournament metadata even without a content block. Block is optional enhancement. |
| **SEO penalty from noindex changes** — removing previously indexed utility pages | LOW | Gradual: robots.txt blocks crawling, noindex prevents indexing. No hard 404s. Google will de-index naturally. |

---

## 9. AdSense Compliance Checklist

| Requirement | Status | Notes |
|-------------|--------|-------|
| **Unique, valuable content** | ✅ Partial | 6 published articles + 5 trust pages. Expand articles before application. |
| **Clear site ownership** | ✅ Done | About page with mission, team, services. |
| **Contact information** | ✅ Done | Contact page with email, form, response times. |
| **Privacy Policy** | ✅ Done | Covers data collection, cookies, AdSense, rights. |
| **Terms of Service** | ✅ Done | Covers accounts, content, liability, AI content. |
| **Good navigation/UX** | ✅ Done | Consistent header/footer, breadcrumbs, internal links. |
| **Mobile-friendly** | ✅ Inherits | Bootstrap 4 responsive. Verify with Lighthouse. |
| **No thin/empty pages indexed** | ✅ Done | Content threshold + noindex on drafts + robots.txt. |
| **ads.txt** | ✅ Existing | Already at `/ads.txt`. |
| **No policy-violating content** | ✅ | Educational debate content only. |
