# NekoTab Organization Workspace Architecture Blueprint

**Status:** Design Specification  
**Date:** 2026-03-06  
**System:** NekoTab v2.10.x (Django 4.x, PostgreSQL, Redis)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Database Design](#2-database-design)
3. [Tenant Detection](#3-tenant-detection)
4. [Routing Design](#4-routing-design)
5. [Project Structure](#5-project-structure)
6. [Migration Strategy](#6-migration-strategy)
7. [Registration Flows](#7-registration-flows)
8. [UI Architecture](#8-ui-architecture)
9. [For-Organizers Page Design](#9-for-organizers-page-design)
10. [Permission System](#10-permission-system)
11. [Scalability](#11-scalability)

---

## 1. System Overview

NekoTab currently operates with a single tenancy model: every subdomain maps to exactly one `Tournament`. This blueprint introduces a **dual-tenancy** system where a subdomain can resolve to either a `Tournament` **or** an `Organization` workspace.

### Two Concurrent Modes

| Mode | URL Pattern | Tenant | Internal Behavior |
|------|-------------|--------|-------------------|
| **Single Tournament** | `bdopen.nekotab.app` | `Tournament(slug="bdopen")` | Existing behavior, unchanged |
| **Organization Workspace** | `dues.nekotab.app` | `Organization(slug="dues")` | New workspace with nested tournament routing |

### Resolution Priority

When a subdomain `foo.nekotab.app` arrives:

1. Check if `foo` matches a `Tournament.slug` → **Tournament mode**
2. Check if `foo` matches an `Organization.slug` → **Organization mode**
3. Neither → **404**

Tournament takes priority because this preserves backward compatibility. Slug collision between Tournament and Organization is prevented at the database level.

---

## 2. Database Design

### 2.1 Model Changes

The existing `Organization` and `OrganizationMembership` models at `tabbycat/organizations/models.py` are already well-structured. The changes needed are **additions**, not rewrites.

#### Organization Model — Add `is_workspace_enabled`

```python
# organizations/models.py — additions to existing Organization model

class Organization(models.Model):
    # ... existing fields: name, slug, created_at, updated_at ...

    # NEW: Controls whether this org gets its own subdomain workspace
    is_workspace_enabled = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name=_("workspace enabled"),
        help_text=_(
            "When enabled, this organization is accessible at "
            "orgslug.nekotab.app as a full workspace. When disabled, "
            "the organization is a backend grouping only (tournaments "
            "in this org still use their own subdomains)."
        ),
    )

    # NEW: Optional vanity fields for the workspace landing page
    description = models.TextField(
        blank=True, default="",
        verbose_name=_("description"),
        help_text=_("Short description shown on the workspace landing page."),
    )
    logo = models.ImageField(
        upload_to='org_logos/', blank=True, null=True,
        verbose_name=_("logo"),
    )
```

**Why `is_workspace_enabled`?** Not every organization needs a subdomain. Existing organizations created via `nekotab.app/organizations/` are backend-only groupings. Only organizations explicitly onboarded through the workspace flow get subdomain routing. This flag is the discriminator.

#### Tournament Model — Add `org_slug` for Intra-Org Routing

The existing `Tournament` model already has:
- `slug` — globally unique `SlugField` (unchanged, still used for single-tournament subdomains)
- `organization` — `ForeignKey` to `Organization` (already required)

**No new fields needed on Tournament.** The existing `slug` field serves dual duty:
- In single-tournament mode: `slug` is the subdomain label
- In organization-workspace mode: `slug` is the URL path segment within the org (`orgslug.nekotab.app/tournaments/<slug>/`)

#### OrganizationMembership — Add `Tabmaster` and `Editor` Roles

```python
# organizations/models.py — replace Role choices

class Role(models.TextChoices):
    OWNER    = 'owner',    _("Owner")
    ADMIN    = 'admin',    _("Admin")
    TABMASTER = 'tabmaster', _("Tabmaster")
    EDITOR   = 'editor',   _("Editor")
    VIEWER   = 'viewer',   _("Viewer")

ROLE_HIERARCHY = {
    Role.OWNER:     5,
    Role.ADMIN:     4,
    Role.TABMASTER: 3,
    Role.EDITOR:    2,
    Role.VIEWER:    1,
}
```

### 2.2 Constraints and Indexes

#### Slug Collision Prevention

Tournament slugs and Organization workspace slugs share the same namespace (subdomain labels). They must never collide.

```python
# New database constraint — implemented as a CheckConstraint + application-level validation

# In Organization.clean() / save():
def clean(self):
    from tournaments.models import Tournament
    if self.is_workspace_enabled and Tournament.objects.filter(slug=self.slug).exists():
        raise ValidationError(
            _("This slug is already in use by a tournament. "
              "Choose a different slug for your organization workspace.")
        )

# In Tournament.clean() / save():
def clean(self):
    from organizations.models import Organization
    if Organization.objects.filter(slug=self.slug, is_workspace_enabled=True).exists():
        raise ValidationError(
            _("This slug is already in use by an organization workspace. "
              "Choose a different tournament slug.")
        )
```

**Why not a shared table?** A cross-table unique constraint cannot be enforced at the PostgreSQL level with standard FK constraints. Instead:

1. **Application-level validation** in `clean()` methods (shown above)
2. **Slug reservation table** for belt-and-suspenders enforcement:

```python
# core/models.py — new model

class SubdomainSlugReservation(models.Model):
    """Guarantees uniqueness of subdomain labels across tournaments and
    organization workspaces.  Inserted transactionally when creating
    either entity."""

    slug = models.SlugField(
        unique=True,
        max_length=80,
        validators=[validate_dns_safe_slug],
        verbose_name=_("slug"),
    )
    tenant_type = models.CharField(
        max_length=20,
        choices=[('tournament', 'Tournament'), ('organization', 'Organization')],
    )
    # Generic pointer — resolved at read time
    tournament = models.OneToOneField(
        'tournaments.Tournament', null=True, blank=True,
        on_delete=models.CASCADE, related_name='slug_reservation',
    )
    organization = models.OneToOneField(
        'organizations.Organization', null=True, blank=True,
        on_delete=models.CASCADE, related_name='slug_reservation',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(tenant_type='tournament', tournament__isnull=False, organization__isnull=True) |
                    models.Q(tenant_type='organization', tournament__isnull=True, organization__isnull=False)
                ),
                name='slug_reservation_exactly_one_target',
            ),
        ]
```

**Insert pattern:** Wrapped in `transaction.atomic()` with `select_for_update()` on the reservation table during tournament/org creation.

#### Tournament Slug Uniqueness Within Organization

For organization-workspace tournaments, the globally-unique `Tournament.slug` constraint already prevents collisions. However, if we later relax global uniqueness (e.g., allowing `dues.nekotab.app/tournaments/open` and `bddc.nekotab.app/tournaments/open`), we would add:

```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=['organization', 'slug'],
            name='unique_tournament_slug_per_org',
        ),
    ]
```

**For now, keep `slug` globally unique.** This is safer during the transition period and ensures any tournament can be accessed as `slug.nekotab.app` if needed.

#### Indexes

```python
# Organization
# slug — already unique (implicit index)
# is_workspace_enabled — db_index=True (for tenant resolution queries)

# SubdomainSlugReservation
# slug — unique (implicit index)

# Tournament
# slug — already unique (implicit index)
# organization_id — implicit FK index
# (organization_id, slug) — add explicit composite index for workspace queries

class Meta:
    indexes = [
        models.Index(fields=['organization', 'slug'], name='idx_tournament_org_slug'),
        models.Index(fields=['organization', 'active'], name='idx_tournament_org_active'),
    ]
```

### 2.3 Entity Relationship Summary

```
Organization 1 ──── * Tournament
     │
     │  1
     │
     * OrganizationMembership
     │
     │  *
     │
     1 User

SubdomainSlugReservation 1 ──── 0..1 Tournament
SubdomainSlugReservation 1 ──── 0..1 Organization
```

---

## 3. Tenant Detection

### 3.1 Middleware Design

The existing `SubdomainTournamentMiddleware` must be replaced with a new `SubdomainTenantMiddleware` that resolves **both** tenant types. This is the single most critical change in the architecture.

```python
# utils/middleware.py — new middleware replacing SubdomainTournamentMiddleware

class SubdomainTenantMiddleware:
    """Resolves subdomain to either a Tournament or an Organization workspace.

    Sets on every request:
        request.tenant_type     — 'tournament' | 'organization' | None
        request.tenant_tournament — Tournament slug (str) or None
        request.tenant_organization — Organization object or None
        request.subdomain_tournament — Tournament slug (backward compat)

    Resolution order:
        1. Tournament.slug exact match → tournament tenant
        2. Tournament.slug case-insensitive match → tournament tenant
        3. Organization.slug exact match (where is_workspace_enabled=True) → org tenant
        4. None found → 404 page
    """

    RESERVED_SUBDOMAINS_DEFAULT = {
        'www', 'admin', 'api', 'static', 'media', 'jet', 'database',
    }

    BAD_PREFIXES = (
        '/static/', '/media/', '/database/', '/api/',
        '/analytics/', '/accounts/', '/campaigns/', '/notifications/',
        '/summernote/', '/jet/', '/organizations/', '/archive/',
        '/forum/', '/motions-bank/', '/passport/',
        '/i18n/', '/jsi18n/',
    )

    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = getattr(settings, 'SUBDOMAIN_TOURNAMENTS_ENABLED', False)
        self.base_domain = getattr(settings, 'SUBDOMAIN_BASE_DOMAIN', '')
        reserved = getattr(settings, 'RESERVED_SUBDOMAINS', None)
        self.reserved = set(reserved) if reserved else self.RESERVED_SUBDOMAINS_DEFAULT
        self.slug_re = _DNS_LABEL_RE

    def _extract_subdomain(self, request):
        """Extract the subdomain label from the Host header. Returns lowercase str or None."""
        try:
            host = request.get_host().split(':')[0].lower()
        except Exception:
            return None
        if not host or not host.endswith(self.base_domain):
            return None
        subpart = host[:-len(self.base_domain)].rstrip('.')
        if not subpart or '.' in subpart:
            return None
        if subpart in self.reserved or not self.slug_re.match(subpart):
            return None
        return subpart

    def _resolve_tenant(self, label):
        """Resolve a subdomain label to a tenant type.

        Returns: ('tournament', slug) | ('organization', Organization) | (None, None)

        Uses a two-tier cache:
            1. Fast lookup: cache key "tenant_type_{label}" → 'tournament' or 'organization'
            2. On miss: query Tournament, then Organization
        """
        cache_key = f"tenant_type_{label}"
        cached = cache.get(cache_key)

        if cached == 'tournament':
            return ('tournament', label)
        elif cached == 'organization':
            org = self._get_org_from_cache(label)
            if org:
                return ('organization', org)
            # Cache was stale; fall through to DB
        elif cached == 'none':
            return (None, None)

        # --- DB resolution ---

        # Priority 1: Tournament (preserves backward compat)
        if (Tournament.objects.filter(slug=label).exists() or
                Tournament.objects.filter(slug__iexact=label).exists()):
            cache.set(cache_key, 'tournament', 300)
            return ('tournament', label)

        # Priority 2: Organization workspace
        try:
            org = Organization.objects.get(slug=label, is_workspace_enabled=True)
            cache.set(cache_key, 'organization', 300)
            cache.set(f"org_obj_{label}", org, 300)
            return ('organization', org)
        except Organization.DoesNotExist:
            pass

        # Nothing found
        cache.set(cache_key, 'none', 15)  # Short TTL for negative results
        return (None, None)

    def _get_org_from_cache(self, label):
        org = cache.get(f"org_obj_{label}")
        if org:
            return org
        try:
            org = Organization.objects.get(slug=label, is_workspace_enabled=True)
            cache.set(f"org_obj_{label}", org, 300)
            return org
        except Organization.DoesNotExist:
            return None

    def __call__(self, request):
        # Initialize all tenant attributes
        request.tenant_type = None
        request.tenant_tournament = None
        request.tenant_organization = None
        request.subdomain_tournament = None  # backward compat

        if not self.enabled or not self.base_domain:
            return self.get_response(request)

        label = self._extract_subdomain(request)
        if not label:
            return self.get_response(request)

        tenant_type, tenant_obj = self._resolve_tenant(label)

        # ── Tournament tenant ──────────────────────────────────────────
        if tenant_type == 'tournament':
            request.tenant_type = 'tournament'
            request.tenant_tournament = label
            request.subdomain_tournament = label  # backward compat

            # Rewrite path exactly as the old SubdomainTournamentMiddleware did
            if not request.path_info.startswith(self.BAD_PREFIXES):
                if not request.path_info.startswith(f'/{label}/'):
                    first_seg = request.path_info.strip('/').split('/')[0] if request.path_info.strip('/') else ''
                    if first_seg and first_seg != label:
                        seg_key = f"subdom_tour_exists_{first_seg}"
                        seg_exists = cache.get(seg_key)
                        if seg_exists is None:
                            seg_exists = Tournament.objects.filter(slug=first_seg).exists()
                            cache.set(seg_key, seg_exists, 300)
                        if seg_exists:
                            return self.get_response(request)
                    new_path = f'/{label}{request.path_info}'
                    request.path_info = new_path
                    request.path = new_path

            return self.get_response(request)

        # ── Organization tenant ────────────────────────────────────────
        if tenant_type == 'organization':
            request.tenant_type = 'organization'
            request.tenant_organization = tenant_obj

            # Do NOT rewrite path_info for org tenants.
            # Org URLs are handled by a dedicated URL config.
            # We swap ROOT_URLCONF to point at org-specific routing.
            request.urlconf = 'organizations.workspace_urls'

            return self.get_response(request)

        # ── Not found ──────────────────────────────────────────────────
        return self._not_found_response(label)

    def _not_found_response(self, label):
        try:
            html = render_to_string('errors/subdomain_404.html', {
                'subdomain': label,
                'base_domain': self.base_domain,
            })
            return HttpResponseNotFound(html)
        except Exception:
            return HttpResponseNotFound(
                f'<h1>Not found</h1>'
                f'<p>No tournament or organization exists at '
                f'<strong>{label}.{self.base_domain}</strong>.</p>'
                f'<p><a href="https://{self.base_domain}/">Go to NekoTab</a></p>'
            )
```

### 3.2 Key Design Decisions in Tenant Detection

**Tournament-first resolution:** Guarantees every existing tournament URL continues to work. A tournament slug will never be accidentally captured as an organization.

**`request.urlconf` override for organizations:** Django supports per-request URL configuration via `request.urlconf`. When an organization subdomain is detected, we set `request.urlconf = 'organizations.workspace_urls'`. This means the entire URL namespace under `orgslug.nekotab.app/` is governed by a separate `urls.py` file, cleanly isolating organization workspace routes from tournament routes.

**No path rewriting for organizations:** Unlike tournament subdomains (which prepend `/<slug>/` to match existing URL patterns), organization subdomains use their own URL config. The path `/tournaments/novice-open` stays as-is.

**Backward-compatible attributes:** `request.subdomain_tournament` is still set for tournament tenants, so all existing views, templates, and middleware continue working without modification.

### 3.3 Middleware Stack Position

```python
# In settings/core.py MIDDLEWARE list:
MIDDLEWARE = [
    # ... security, session, auth (unchanged) ...
    'utils.middleware.SubdomainTenantMiddleware',  # REPLACES SubdomainTournamentMiddleware
    'utils.middleware.DebateMiddleware',            # Unchanged — only activates for tournament routes
    # ... rest unchanged ...
]
```

`DebateMiddleware` does not need modification. It only activates when `tournament_slug` is in `view_kwargs`, which only happens within tournament URL patterns. Organization workspace URLs never have `tournament_slug` in their kwargs at the top level.

### 3.4 Cache Strategy

| Cache Key | TTL | Stores |
|-----------|-----|--------|
| `tenant_type_{label}` | 300s (positive), 15s (negative) | `'tournament'` / `'organization'` / `'none'` |
| `org_obj_{label}` | 300s | Serialized `Organization` object |
| `subdom_tour_exists_{label}` | 300s (positive), 15s (negative) | Boolean (legacy compat) |

Cache is invalidated on:
- Tournament creation/deletion → delete `tenant_type_{slug}` and `subdom_tour_exists_{slug}`
- Organization creation/deletion/`is_workspace_enabled` toggle → delete `tenant_type_{slug}` and `org_obj_{slug}`

Wire these via `post_save` / `post_delete` signals on the respective models.

---

## 4. Routing Design

### 4.1 Root URL Config (unchanged, `tabbycat/urls.py`)

The root URL config at `nekotab.app` (bare domain, no subdomain) remains unchanged. It handles:

```
/                                → PublicSiteIndexView (homepage)
/create/                         → CreateTournamentView (single tournament creation)
/accounts/                       → User auth (login, signup, etc.)
/organizations/                  → Org management (existing path-based UI)
/register/tournament/            → NEW — Single tournament registration flow
/register/organization/          → NEW — Organization workspace registration flow
/for-organizers/                 → NEW — Marketing/decision page
/<slug:tournament_slug>/         → Tournament routes (when accessed via path)
```

Add these new paths to `tabbycat/urls.py`:

```python
# In tabbycat/urls.py — add before the tournament catch-all

# New onboarding flows
path('register/tournament/',
    tournaments.views.RegisterTournamentView.as_view(),
    name='register-tournament'),
path('register/organization/',
    organizations.views.RegisterOrganizationView.as_view(),
    name='register-organization'),

# Marketing page
path('for-organizers/',
    TemplateView.as_view(template_name='marketing/for_organizers.html'),
    name='for-organizers'),
```

### 4.2 Organization Workspace URL Config (NEW)

This file is loaded by `request.urlconf = 'organizations.workspace_urls'` when an organization subdomain is detected.

```python
# organizations/workspace_urls.py

from django.urls import include, path

from . import workspace_views

app_name = 'workspace'

urlpatterns = [
    # ── Workspace root (dashboard) ─────────────────────────────────────
    path('',
        workspace_views.WorkspaceDashboardView.as_view(),
        name='dashboard'),

    # ── Tournaments ────────────────────────────────────────────────────
    path('tournaments/',
        workspace_views.TournamentListView.as_view(),
        name='tournament-list'),
    path('tournaments/new/',
        workspace_views.TournamentCreateView.as_view(),
        name='tournament-create'),
    path('tournaments/<slug:tournament_slug>/',
        workspace_views.TournamentRedirectView.as_view(),
        name='tournament-redirect'),

    # ── Members ────────────────────────────────────────────────────────
    path('members/',
        workspace_views.MembersView.as_view(),
        name='members'),
    path('members/invite/',
        workspace_views.InviteMemberView.as_view(),
        name='invite-member'),
    path('members/<int:membership_id>/',
        workspace_views.MemberDetailView.as_view(),
        name='member-detail'),

    # ── Settings ───────────────────────────────────────────────────────
    path('settings/',
        workspace_views.SettingsView.as_view(),
        name='settings'),
    path('settings/billing/',
        workspace_views.BillingView.as_view(),
        name='billing'),

    # ── Archive ────────────────────────────────────────────────────────
    path('archive/',
        workspace_views.ArchiveView.as_view(),
        name='archive'),

    # ── Shared Resources ───────────────────────────────────────────────
    path('judges/',
        workspace_views.SharedJudgePoolView.as_view(),
        name='judge-pool'),

    # ── Nested tournament access ───────────────────────────────────────
    # When a user accesses dues.nekotab.app/tournaments/novice-open/admin/draw/
    # we need to route into the existing tournament URL patterns.
    path('tournaments/<slug:tournament_slug>/',
        include('tournaments.urls')),

    # ── Static/system routes (must work on org subdomains too) ─────────
    path('accounts/', include('users.urls')),
    path('i18n/', include('django.conf.urls.i18n')),
    path('jsi18n/',
        workspace_views.JavaScriptCatalog.as_view(domain="djangojs"),
        name='javascript-catalog'),

    # API access scoped to org
    path('api/', include('api.urls')),
]
```

### 4.3 Tournament Access Within Organization Workspace

When a user navigates to `dues.nekotab.app/tournaments/novice-open/admin/draw/`:

1. `SubdomainTenantMiddleware` detects `dues` as an organization → sets `request.urlconf = 'organizations.workspace_urls'`
2. Django resolves `tournaments/novice-open/admin/draw/` against `workspace_urls.py`
3. The URL matches `path('tournaments/<slug:tournament_slug>/', include('tournaments.urls'))`
4. This hits the existing tournament URL patterns — `DebateMiddleware.process_view()` fires, resolves the tournament, checks access
5. The view renders identically to the single-tournament case

**Critical:** The `DebateMiddleware` must verify that the tournament being accessed belongs to the organization on the subdomain:

```python
# Addition to DebateMiddleware.process_view()

# After resolving the tournament object:
if hasattr(request, 'tenant_organization') and request.tenant_organization:
    if request.tournament.organization_id != request.tenant_organization.pk:
        # Tournament exists but doesn't belong to this org workspace
        return self._tournament_not_found_response(slug, request)
```

This prevents `evil-org.nekotab.app/tournaments/some-other-orgs-tournament/` from leaking data.

### 4.4 URL Summary Table

| URL | Mode | Handler |
|-----|------|---------|
| `nekotab.app/` | Base domain | `PublicSiteIndexView` |
| `nekotab.app/for-organizers/` | Base domain | Marketing page |
| `nekotab.app/register/tournament/` | Base domain | Single tournament onboarding |
| `nekotab.app/register/organization/` | Base domain | Org workspace onboarding |
| `bdopen.nekotab.app/` | Tournament tenant | Tournament public index |
| `bdopen.nekotab.app/admin/draw/` | Tournament tenant | Tournament admin (existing) |
| `dues.nekotab.app/` | Org tenant | Workspace dashboard |
| `dues.nekotab.app/tournaments/` | Org tenant | Tournament list |
| `dues.nekotab.app/tournaments/novice-open/` | Org tenant → tournament | Tournament within org |
| `dues.nekotab.app/tournaments/novice-open/admin/draw/` | Org tenant → tournament | Tournament admin within org |
| `dues.nekotab.app/members/` | Org tenant | Members management |
| `dues.nekotab.app/settings/` | Org tenant | Org settings |

---

## 5. Project Structure

### 5.1 App Responsibilities

```
tabbycat/
├── core/                          # NEW — shared models (SubdomainSlugReservation)
│   ├── models.py
│   └── utils.py
│
├── organizations/                 # EXTENDED — workspace views + URLs
│   ├── models.py                  # Organization, OrganizationMembership (extended)
│   ├── views.py                   # Existing org management (path-based, unchanged)
│   ├── workspace_views.py         # NEW — views for subdomain org workspace
│   ├── workspace_urls.py          # NEW — URL config loaded via request.urlconf
│   ├── workspace_mixins.py        # NEW — access control for workspace views
│   ├── signals.py                 # Extended — cache invalidation for tenant resolution
│   ├── urls.py                    # Existing (unchanged)
│   ├── forms.py                   # NEW — workspace-specific forms
│   ├── admin.py                   # Existing (unchanged)
│   └── templates/
│       └── organizations/
│           ├── workspace/         # NEW — workspace templates
│           │   ├── base.html      # Workspace layout with sidebar
│           │   ├── dashboard.html
│           │   ├── tournament_list.html
│           │   ├── tournament_create.html
│           │   ├── members.html
│           │   ├── settings.html
│           │   └── archive.html
│           ├── list.html          # Existing
│           ├── detail.html        # Existing
│           └── ...
│
├── tournaments/                   # LIGHTLY MODIFIED
│   ├── models.py                  # Add org_active composite index, clean() validation
│   ├── views.py                   # Add RegisterTournamentView
│   └── ...                        # Everything else unchanged
│
├── users/                         # LIGHTLY MODIFIED
│   ├── permissions.py             # Extended permission logic for new roles
│   └── ...
│
├── utils/
│   ├── middleware.py               # SubdomainTenantMiddleware replaces SubdomainTournamentMiddleware
│   └── ...
│
├── templates/
│   ├── marketing/
│   │   └── for_organizers.html    # NEW — marketing page
│   └── errors/
│       └── subdomain_404.html     # Updated to handle both tenant types
│
└── settings/
    └── core.py                    # Middleware swap
```

### 5.2 New `core` App

```python
# core/models.py

class SubdomainSlugReservation(models.Model):
    """Cross-entity unique subdomain label registry."""
    # ... as defined in Section 2.2 ...
```

This app is intentionally minimal. It exists to hold cross-cutting models that don't belong in `tournaments` or `organizations` to avoid circular imports.

### 5.3 Workspace Mixins

```python
# organizations/workspace_mixins.py

class WorkspaceAccessMixin:
    """Base mixin for all workspace views.
    Requires authenticated user + membership in the request's organization."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        org = getattr(request, 'tenant_organization', None)
        if not org:
            raise Http404
        self.organization = org
        self.membership = OrganizationMembership.objects.filter(
            organization=org, user=request.user,
        ).first()
        if not self.membership and not request.user.is_superuser:
            raise Http404
        return super().dispatch(request, *args, **kwargs)


class WorkspaceAdminMixin(WorkspaceAccessMixin):
    """Requires ADMIN or OWNER role."""

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if hasattr(self, 'membership') and self.membership:
            if not self.membership.has_role_at_least(OrganizationMembership.Role.ADMIN):
                return HttpResponseForbidden("Admin access required.")
        return response


class WorkspaceOwnerMixin(WorkspaceAccessMixin):
    """Requires OWNER role."""

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if hasattr(self, 'membership') and self.membership:
            if self.membership.role != OrganizationMembership.Role.OWNER:
                return HttpResponseForbidden("Owner access required.")
        return response
```

---

## 6. Migration Strategy

### 6.1 Phased Rollout

**Phase 1 — Database additions (zero downtime)**

1. Add `is_workspace_enabled`, `description`, `logo` fields to `Organization` model
2. Add `Tabmaster` and `Editor` to `OrganizationMembership.Role` choices
3. Create `SubdomainSlugReservation` model
4. Run `makemigrations` and `migrate`
5. Backfill `SubdomainSlugReservation` rows for all existing tournaments:

```python
# Data migration
from django.db import migrations

def backfill_slug_reservations(apps, schema_editor):
    Tournament = apps.get_model('tournaments', 'Tournament')
    SubdomainSlugReservation = apps.get_model('core', 'SubdomainSlugReservation')
    for t in Tournament.objects.all():
        SubdomainSlugReservation.objects.get_or_create(
            slug=t.slug.lower(),
            defaults={
                'tenant_type': 'tournament',
                'tournament': t,
            }
        )

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
        ('tournaments', 'XXXX_last_migration'),
    ]
    operations = [
        migrations.RunPython(backfill_slug_reservations, migrations.RunPython.noop),
    ]
```

**Phase 2 — Middleware swap (feature-gated)**

1. Add `SubdomainTenantMiddleware` alongside the old `SubdomainTournamentMiddleware`
2. Gate activation behind a new setting: `ORGANIZATION_WORKSPACES_ENABLED = False`
3. When flag is `False`, the new middleware behaves identically to the old one (tournament-only resolution)
4. Deploy, verify zero regressions via existing test suite
5. Flip `ORGANIZATION_WORKSPACES_ENABLED = True` in production

```python
# In SubdomainTenantMiddleware._resolve_tenant():
if not getattr(settings, 'ORGANIZATION_WORKSPACES_ENABLED', False):
    # Legacy mode: only resolve tournaments
    if (...tournament exists...):
        return ('tournament', label)
    return (None, None)
```

**Phase 3 — Workspace UI**

1. Create `workspace_urls.py`, `workspace_views.py`, workspace templates
2. Add registration flows (`/register/tournament/`, `/register/organization/`)
3. Add marketing page (`/for-organizers/`)
4. Deploy behind feature flag or admin-only access

**Phase 4 — General availability**

1. Remove old `SubdomainTournamentMiddleware` code
2. Remove feature gates
3. Announce organization workspaces publicly

### 6.2 Existing Tournament Safety Guarantees

| Concern | Guarantee |
|---------|-----------|
| Existing tournament URLs work? | Yes — tournament takes resolution priority |
| Tournament views modified? | No — `DebateMiddleware` unchanged |
| `request.subdomain_tournament` still set? | Yes — backward compat attribute |
| Tournament permissions change? | No — existing `has_permission()` path unchanged |
| Tournament database schema changes? | Indexes only — no field changes |

### 6.3 Rollback Plan

If issues are discovered after Phase 2:

1. Set `ORGANIZATION_WORKSPACES_ENABLED = False` — instantly reverts to tournament-only mode
2. Or: swap middleware back to `SubdomainTournamentMiddleware` in settings (requires deploy)

Database changes are purely additive (new fields, new models) and do not affect existing data.

---

## 7. Registration Flows

### 7.1 Flow A — Single Tournament Registration

**Path:** `nekotab.app/register/tournament/`

This is a streamlined version of the existing `CreateTournamentView` (currently at `/create/`).

#### Step 1: Account Creation (if not authenticated)

```
Fields:
  - Username
  - Email
  - Password
  - Confirm Password
```

If already logged in, skip to Step 2.

#### Step 2: Tournament Details

```
Fields:
  - Tournament Name          (CharField, max 100)
  - Tournament Slug          (SlugField, auto-generated from name, editable)
  - Format                   (Select: BP, AP, CP, Worlds, Custom)
  - Expected Team Count      (IntegerField, optional — influences default settings)
  - Start Date               (DateField, optional)

Validation:
  - Slug is DNS-safe (validate_dns_safe_slug)
  - Slug not in RESERVED_SUBDOMAINS
  - Slug not in SubdomainSlugReservation
  - Slug not matching any Organization.slug where is_workspace_enabled=True
```

#### Step 3: Confirmation

```
Preview:
  "Your tournament will be accessible at:"
  [bdopen.nekotab.app]

  "You'll be the tournament owner with full admin access."
```

#### Post-Creation

1. Create `Organization` (auto-generated, `is_workspace_enabled=False`, name = tournament name)
2. Create `OrganizationMembership` (user = OWNER)
3. Create `Tournament` (organization = auto-org, owner = user)
4. Create `SubdomainSlugReservation` (slug = tournament slug, tenant_type = 'tournament')
5. Redirect to `slug.nekotab.app/admin/` (setup wizard)

**Why auto-create an Organization?** Every tournament must belong to an Organization (FK is non-nullable). For single-tournament users, a "phantom" org is created automatically. This org is invisible to the user unless they later upgrade to workspace mode.

### 7.2 Flow B — Organization Workspace Registration

**Path:** `nekotab.app/register/organization/`

#### Step 1: Account Creation (if not authenticated)

Same as Flow A.

#### Step 2: Organization Details

```
Fields:
  - Organization Name        (CharField, max 200)
  - Organization Slug        (SlugField, auto-generated, editable)
  - Description              (TextField, optional)
  - Logo                     (ImageField, optional)

Validation:
  - Slug is DNS-safe
  - Slug not in RESERVED_SUBDOMAINS
  - Slug not in SubdomainSlugReservation
  - Slug not matching any Tournament.slug
```

#### Step 3: Invite Members (Optional)

```
Fields:
  - Email addresses          (comma-separated or one-per-line)
  - Role for invitees        (Select: Admin, Tabmaster, Editor, Viewer)

This step can be skipped.
```

#### Step 4: Confirmation

```
Preview:
  "Your organization workspace will be at:"
  [dues.nekotab.app]

  "You'll be the organization owner."
  "You can create unlimited tournaments inside this workspace."
```

#### Post-Creation

1. Create `Organization` (is_workspace_enabled=True)
2. Create `OrganizationMembership` (user = OWNER)
3. Create `SubdomainSlugReservation` (slug = org slug, tenant_type = 'organization')
4. Send invitation emails (if members were invited)
5. Redirect to `orgslug.nekotab.app/tournaments/new/`

### 7.3 View Implementation Sketch

```python
# organizations/views.py — new view

class RegisterOrganizationView(View):
    """Multi-step org workspace registration."""

    def get(self, request):
        if not request.user.is_authenticated:
            return render(request, 'registration/org_step1_account.html')
        return render(request, 'registration/org_step2_details.html', {
            'form': OrganizationRegistrationForm(),
        })

    def post(self, request):
        form = OrganizationRegistrationForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, 'registration/org_step2_details.html', {
                'form': form,
            })

        with transaction.atomic():
            org = form.save()
            OrganizationMembership.objects.create(
                organization=org,
                user=request.user,
                role=OrganizationMembership.Role.OWNER,
            )
            SubdomainSlugReservation.objects.create(
                slug=org.slug.lower(),
                tenant_type='organization',
                organization=org,
            )

        workspace_url = f"https://{org.slug}.{settings.SUBDOMAIN_BASE_DOMAIN}/tournaments/new/"
        return redirect(workspace_url)
```

---

## 8. UI Architecture

### 8.1 Organization Workspace Layout

The workspace uses a fixed sidebar + main content area, distinct from the tournament admin layout.

```
┌──────────────────────────────────────────────────────────────┐
│  [Logo] dues                                    [User Menu]  │
├──────────────┬───────────────────────────────────────────────┤
│              │                                               │
│  Dashboard   │   Main Content Area                           │
│              │                                               │
│  Tournaments │   (varies by route)                           │
│    ├ Active  │                                               │
│    └ Create  │                                               │
│              │                                               │
│  Judges      │                                               │
│              │                                               │
│  Members     │                                               │
│              │                                               │
│  Settings    │                                               │
│              │                                               │
│  Archive     │                                               │
│              │                                               │
├──────────────┤                                               │
│  [Org Plan]  │                                               │
│  Free Tier   │                                               │
└──────────────┴───────────────────────────────────────────────┘
```

#### Sidebar Navigation

```html
<!-- organizations/templates/organizations/workspace/base.html -->

<nav class="workspace-sidebar">
  <div class="sidebar-brand">
    {% if organization.logo %}
      <img src="{{ organization.logo.url }}" alt="" class="sidebar-logo">
    {% endif %}
    <span class="sidebar-org-name">{{ organization.name }}</span>
  </div>

  <ul class="sidebar-nav">
    <li class="{% if active_tab == 'dashboard' %}active{% endif %}">
      <a href="{% url 'workspace:dashboard' %}">
        <i class="bi bi-grid"></i> Dashboard
      </a>
    </li>
    <li class="{% if active_tab == 'tournaments' %}active{% endif %}">
      <a href="{% url 'workspace:tournament-list' %}">
        <i class="bi bi-trophy"></i> Tournaments
      </a>
    </li>
    <li class="{% if active_tab == 'judges' %}active{% endif %}">
      <a href="{% url 'workspace:judge-pool' %}">
        <i class="bi bi-people"></i> Judges
      </a>
    </li>
    <li class="{% if active_tab == 'members' %}active{% endif %}">
      <a href="{% url 'workspace:members' %}">
        <i class="bi bi-person-gear"></i> Members
      </a>
    </li>
    <li class="{% if active_tab == 'settings' %}active{% endif %}">
      <a href="{% url 'workspace:settings' %}">
        <i class="bi bi-gear"></i> Settings
      </a>
    </li>
    <li class="{% if active_tab == 'archive' %}active{% endif %}">
      <a href="{% url 'workspace:archive' %}">
        <i class="bi bi-archive"></i> Archive
      </a>
    </li>
  </ul>
</nav>
```

### 8.2 Workspace Dashboard (`/`)

```
┌─────────────────────────────────────────────────────────┐
│ Welcome to DUES Workspace                               │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐          │
│  │ 3 Active  │  │ 12 Judges │  │ 5 Members │          │
│  │Tournaments│  │ in Pool   │  │           │          │
│  └───────────┘  └───────────┘  └───────────┘          │
│                                                         │
│  ── Active Tournaments ──────────────────────────────   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ Novice Open 2026         Round 4 / 6            │   │
│  │ 32 teams · 15 judges     Draw released           │   │
│  │ [Go to Admin] [View Public]                      │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ National Qualifier       Round 2 / 5            │   │
│  │ 64 teams · 28 judges     Results pending         │   │
│  │ [Go to Admin] [View Public]                      │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  [+ Create New Tournament]                              │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 8.3 Tournaments Index (`/tournaments/`)

```
┌─────────────────────────────────────────────────────────┐
│ Tournaments                              [+ Create New] │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Filter: [All ▾]  [Active ▾]  Search: [____________]   │
│                                                         │
│  ── Active ─────────────────────────────────────────    │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Novice Open 2026                                  │  │
│  │ novice-open · BP · 32 teams                       │  │
│  │ Created Jan 15, 2026 · Round 4 of 6               │  │
│  │ [Admin] [Public Page] [Settings] [⋮]              │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │ National Qualifier 2026                           │  │
│  │ national-qualifier · AP · 64 teams                │  │
│  │ Created Feb 1, 2026 · Round 2 of 5                │  │
│  │ [Admin] [Public Page] [Settings] [⋮]              │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ── Completed ──────────────────────────────────────    │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Fall Invitational 2025                            │  │
│  │ fall-invitational · BP · 48 teams                 │  │
│  │ Completed Dec 10, 2025                            │  │
│  │ [View Results] [Archive] [⋮]                      │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 8.4 Tournament-Within-Org Behavior

When a user clicks into a tournament (e.g., "Admin" on "Novice Open"), they navigate to:

`dues.nekotab.app/tournaments/novice-open/admin/`

The existing tournament admin UI renders in full. The only visual change is:

1. A **breadcrumb bar** at the top showing: `DUES > Tournaments > Novice Open > Admin`
2. A **"Back to Workspace"** link in the navbar that returns to `dues.nekotab.app/`

This is injected via template context by `DebateMiddleware` detecting `request.tenant_organization`:

```python
# In DebateMiddleware or a context processor:
def debate_context(request):
    ctx = {}
    if getattr(request, 'tenant_organization', None):
        ctx['workspace_org'] = request.tenant_organization
        ctx['workspace_url'] = f"https://{request.tenant_organization.slug}.{settings.SUBDOMAIN_BASE_DOMAIN}/"
    return ctx
```

---

## 9. For-Organizers Page Design

**Path:** `nekotab.app/for-organizers/`

### Section 1 — Hero

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│         Run Debate Tournaments at Any Scale                 │
│                                                             │
│   Whether you're running a single competition or            │
│   managing a full debate program, NekoTab has you covered.  │
│                                                             │
│   [Get Started Free]          [See How It Works ↓]          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

Copy: Focus on the audience (organizers), not features. CTA is "Get Started Free" → scrolls to decision cards.

### Section 2 — Decision Cards

Two side-by-side cards helping the organizer self-select.

```
┌──────────────────────────────┐  ┌──────────────────────────────┐
│                              │  │                              │
│  🏆 Single Tournament        │  │  🏢 Organization Workspace    │
│                              │  │                              │
│  Running one event?          │  │  Managing a debate program?  │
│  Get set up in minutes.      │  │  Run many events from one    │
│                              │  │  central hub.                │
│  • One tournament            │  │                              │
│  • Your own subdomain        │  │  • Unlimited tournaments     │
│  • Full tabulation suite     │  │  • Team-based access control │
│  • Public results page       │  │  • Shared judge pools        │
│                              │  │  • Organization dashboard    │
│  slug.nekotab.app            │  │  org.nekotab.app             │
│                              │  │                              │
│  [Create Tournament →]       │  │  [Create Workspace →]        │
│                              │  │                              │
│  Free                        │  │  Free to start               │
│                              │  │                              │
└──────────────────────────────┘  └──────────────────────────────┘
```

- "Create Tournament" → `nekotab.app/register/tournament/`
- "Create Workspace" → `nekotab.app/register/organization/`

### Section 3 — Comparison Table

```
┌──────────────────────────────┬──────────────┬──────────────────┐
│ Feature                      │ Single       │ Organization     │
├──────────────────────────────┼──────────────┼──────────────────┤
│ Tournaments                  │ 1            │ Unlimited        │
│ Custom subdomain             │ ✓            │ ✓                │
│ Full tabulation              │ ✓            │ ✓                │
│ Public results               │ ✓            │ ✓                │
│ Team members                 │ —            │ Up to 50         │
│ Role-based access            │ Basic        │ 5 roles          │
│ Shared judge pool            │ —            │ ✓                │
│ Organization dashboard       │ —            │ ✓                │
│ Tournament archive           │ —            │ ✓                │
│ Debater passport             │ —            │ Coming soon      │
│ API access                   │ ✓            │ ✓                │
│ Upgrade path                 │ → Org        │ —                │
└──────────────────────────────┴──────────────┴──────────────────┘
```

### Section 4 — Organization Workspace Walkthrough

Visual walkthrough of the workspace UI (screenshots or illustrations).

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│     Your Debate Program, One Dashboard                      │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ [Screenshot: Workspace dashboard with tournament      │  │
│  │  cards, member count, and judge pool stats]           │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ① Create your organization workspace                       │
│  ② Invite your tabulation team                              │
│  ③ Create tournaments as needed                             │
│  ④ Share judges across events                               │
│  ⑤ Review results in your archive                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Section 5 — Social Proof / Use Cases

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  "Trusted by debate societies worldwide"                    │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ National │  │ University│  │ Circuit  │  │ Training │   │
│  │ Federations│  │ Societies│  │ Series  │  │ Programs │   │
│  │          │  │          │  │          │  │          │   │
│  │ Run your │  │ Manage   │  │ Link     │  │ Track    │   │
│  │ national │  │ semester │  │ events   │  │ student  │   │
│  │ circuit  │  │ events   │  │ across   │  │ progress │   │
│  │ from one │  │ with your│  │ regions  │  │ across   │   │
│  │ workspace│  │ exec team│  │          │  │ events   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Section 6 — Workflow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  How It Works                                               │
│                                                             │
│  [Sign Up] ──→ [Choose Mode] ──→ [Set Up] ──→ [Go Live]    │
│                                                             │
│  Create your     Single event     Configure      Your       │
│  free account    or workspace?    your setup     tournament │
│                                                  is live    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Section 7 — Final CTA

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│         Ready to run your next tournament?                  │
│                                                             │
│   [Create a Single Tournament]  [Create an Organization]    │
│                                                             │
│   Open-source · Self-hostable · Production-ready            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 10. Permission System

### 10.1 Organization Role Definitions

| Role | Level | Scope | Capabilities |
|------|-------|-------|-------------|
| **Owner** | 5 | Organization-wide | Full control: delete org, manage billing, transfer ownership, manage all members (including promoting to Owner), full access to all tournaments |
| **Admin** | 4 | Organization-wide | Manage members (except Owner changes), create/delete tournaments, full admin access to all tournaments, edit org settings |
| **Tabmaster** | 3 | Tournament-scoped | Full tournament admin access (draw, results, settings) for assigned tournaments, view member list, cannot create tournaments or manage org settings |
| **Editor** | 2 | Tournament-scoped | Edit tournament data (enter results, manage availability, update motions) but cannot modify tournament settings, generate draws, or confirm rounds |
| **Viewer** | 1 | Read-only | View all tournaments and their data (including admin views) but cannot modify anything |

### 10.2 Role-to-Permission Mapping

The existing `users/permissions.py` has 100+ granular `Permission` choices. Organization roles map to these as follows:

```python
# organizations/permissions.py — new file

from users.permissions import Permission

# Permissions granted to each organization role across ALL org tournaments

ROLE_PERMISSIONS = {
    'owner': '__all__',   # All permissions (short-circuit in has_permission)
    'admin': '__all__',   # All permissions (short-circuit in has_permission)

    'tabmaster': {
        # Full tournament admin — everything except org-level settings
        Permission.VIEW_TEAMS, Permission.ADD_TEAMS, Permission.VIEW_DECODED_TEAMS,
        Permission.VIEW_ADJUDICATORS, Permission.ADD_ADJUDICATORS,
        Permission.VIEW_ROOMS, Permission.ADD_ROOMS,
        Permission.VIEW_INSTITUTIONS, Permission.ADD_INSTITUTIONS,
        Permission.VIEW_PARTICIPANTS, Permission.VIEW_PARTICIPANT_DECODED,
        Permission.VIEW_PARTICIPANT_CONTACT, Permission.VIEW_PARTICIPANT_GENDER,
        Permission.VIEW_ROUNDAVAILABILITIES, Permission.EDIT_ROUNDAVAILABILITIES,
        Permission.VIEW_DEBATE, Permission.VIEW_ADMIN_DRAW,
        Permission.GENERATE_DEBATE, Permission.DELETE_DEBATE,
        Permission.EDIT_DEBATETEAMS, Permission.EDIT_DEBATEADJUDICATORS,
        Permission.VIEW_DEBATEADJUDICATORS,
        Permission.VIEW_ROOMALLOCATIONS, Permission.EDIT_ROOMALLOCATIONS,
        Permission.VIEW_BALLOTSUBMISSIONS, Permission.EDIT_BALLOTSUBMISSIONS,
        Permission.ADD_BALLOTSUBMISSIONS, Permission.MARK_BALLOTSUBMISSIONS,
        Permission.VIEW_RESULTS,
        Permission.VIEW_MOTION, Permission.EDIT_MOTION,
        Permission.RELEASE_DRAW, Permission.RELEASE_MOTION,
        Permission.VIEW_SETTINGS, Permission.EDIT_SETTINGS,
        Permission.EDIT_BREAK_CATEGORIES, Permission.GENERATE_BREAK,
        Permission.VIEW_BREAK, Permission.VIEW_BREAK_OVERVIEW,
        Permission.CONFIRM_ROUND, Permission.EDIT_ROUND,
        Permission.CREATE_ROUND, Permission.DELETE_ROUND,
        Permission.VIEW_FEEDBACK, Permission.EDIT_FEEDBACK_CONFIRM,
        Permission.VIEW_FEEDBACK_OVERVIEW,
        Permission.VIEW_CHECKIN, Permission.EDIT_PARTICIPANT_CHECKIN,
        Permission.SEND_EMAILS,
        Permission.VIEW_REGISTRATION,
        Permission.EDIT_QUESTIONS,
        # ... (comprehensive list)
    },

    'editor': {
        # Data entry — results, motions, availability, checkins
        Permission.VIEW_TEAMS, Permission.VIEW_ADJUDICATORS,
        Permission.VIEW_ROOMS, Permission.VIEW_INSTITUTIONS,
        Permission.VIEW_PARTICIPANTS,
        Permission.VIEW_ROUNDAVAILABILITIES, Permission.EDIT_ROUNDAVAILABILITIES,
        Permission.VIEW_DEBATE,
        Permission.VIEW_BALLOTSUBMISSIONS, Permission.EDIT_OLD_BALLOTSUBMISSIONS,
        Permission.ADD_BALLOTSUBMISSIONS,
        Permission.VIEW_NEW_BALLOTSUBMISSIONS,
        Permission.VIEW_RESULTS,
        Permission.VIEW_MOTION,
        Permission.VIEW_FEEDBACK, Permission.ADD_FEEDBACK,
        Permission.VIEW_CHECKIN, Permission.EDIT_PARTICIPANT_CHECKIN,
        Permission.EDIT_ROOM_CHECKIN,
        Permission.VIEW_REGISTRATION,
    },

    'viewer': {
        # Read-only access to admin views
        Permission.VIEW_TEAMS, Permission.VIEW_ADJUDICATORS,
        Permission.VIEW_ROOMS, Permission.VIEW_INSTITUTIONS,
        Permission.VIEW_PARTICIPANTS,
        Permission.VIEW_ROUNDAVAILABILITIES,
        Permission.VIEW_DEBATE,
        Permission.VIEW_BALLOTSUBMISSIONS,
        Permission.VIEW_NEW_BALLOTSUBMISSIONS,
        Permission.VIEW_RESULTS,
        Permission.VIEW_MOTION,
        Permission.VIEW_FEEDBACK, Permission.VIEW_FEEDBACK_OVERVIEW,
        Permission.VIEW_BREAK, Permission.VIEW_BREAK_OVERVIEW,
        Permission.VIEW_CHECKIN,
        Permission.VIEW_REGISTRATION,
    },
}
```

### 10.3 Updated `has_permission()` Logic

The existing `has_permission()` in `users/permissions.py` already handles org OWNER and ADMIN with a short-circuit. Extend it for the new roles:

```python
# In users/permissions.py — modified has_permission()

def has_permission(user, permission, tournament):
    if user.is_anonymous:
        return False
    if user.is_superuser:
        return True
    if hasattr(tournament, 'owner_id') and tournament.owner_id == user.pk:
        return True

    # Organization-level access
    if hasattr(tournament, 'organization_id') and tournament.organization_id:
        from organizations.models import OrganizationMembership
        from organizations.permissions import ROLE_PERMISSIONS

        org_membership = OrganizationMembership.objects.filter(
            organization_id=tournament.organization_id,
            user=user,
        ).first()

        if org_membership is not None:
            role_perms = ROLE_PERMISSIONS.get(org_membership.role)

            # Owner/Admin: unconditional access
            if role_perms == '__all__':
                return True

            # Tabmaster/Editor/Viewer: check specific permission
            if isinstance(role_perms, set) and permission in role_perms:
                return True

            # If the role doesn't grant this permission, fall through
            # to per-tournament permission checks below (allows
            # additional grants via UserPermission or Group)

    # ... existing per-tournament permission logic (unchanged) ...
```

### 10.4 Workspace-Level vs Tournament-Level Permissions

| Action | Required Role |
|--------|--------------|
| View workspace dashboard | Any member (Viewer+) |
| View tournament list | Any member (Viewer+) |
| Create a tournament | Admin+ |
| Delete a tournament | Admin+ |
| Access tournament admin panel | Tabmaster+ (or explicit UserPermission) |
| Enter ballot results | Editor+ (or explicit UserPermission) |
| Generate draw | Tabmaster+ |
| Manage members | Admin+ |
| Change org settings | Admin+ |
| Change billing/plan | Owner only |
| Delete organization | Owner only |
| Transfer ownership | Owner only |

### 10.5 Permission Override

Organization roles set a **baseline**. Per-tournament permissions can **augment** but not **reduce** org-level grants. This means:

- A Viewer in the org can be granted `EDIT_BALLOTSUBMISSIONS` on a specific tournament via `UserPermission` → they can enter results for that tournament only
- A Tabmaster cannot have their org-level permissions removed for a specific tournament (the org role is a floor, not a ceiling)

---

## 11. Scalability

### 11.1 Shared Judge Pools

**Data model:**

```python
# organizations/models.py

class SharedJudge(models.Model):
    """A judge registered at the organization level, importable into tournaments."""
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='shared_judges')
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    institution = models.ForeignKey('participants.Institution', null=True, blank=True, on_delete=models.SET_NULL)
    base_score = models.FloatField(default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('organization', 'email')]
```

**Workflow:** When creating a tournament within a workspace, the "Add Adjudicators" step includes an "Import from Organization Pool" option that copies `SharedJudge` records into the tournament's `Adjudicator` table. Feedback scores from tournaments flow back to update `SharedJudge.base_score` over time.

### 11.2 Debater Passports

The existing `passport` app (`tabbycat/passport/`) provides the foundation. The organization workspace enables:

- **Cross-tournament identity:** A debater participates in multiple tournaments within an org. The passport links these records.
- **Data model extension:** `Passport.organization` FK — ties the passport to an org, aggregating results across that org's tournaments.
- **Privacy:** Debaters opt in to passport visibility. Organization members with Viewer+ role can see aggregated stats.

### 11.3 Organization Archives

The existing `retention` and `importer.urls_archive` apps handle tournament data lifecycle. Organization workspace adds:

- **Archive index:** `dues.nekotab.app/archive/` lists all completed (inactive) tournaments
- **Bulk export:** Organization admins can export all tournament data in a single archive
- **Retention override:** Organization tournaments can have `retention_exempt=True` set at the org level (org Admin+ can toggle), preventing auto-deletion

### 11.4 Multi-Event Circuits

A circuit is a sequence of tournaments with cumulative standings.

```python
# organizations/models.py — future

class Circuit(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='circuits')
    name = models.CharField(max_length=200)
    slug = models.SlugField()
    tournaments = models.ManyToManyField('tournaments.Tournament', through='CircuitTournament')
    scoring_system = models.CharField(max_length=50)  # e.g., 'cumulative_wins', 'points_based'

    class Meta:
        unique_together = [('organization', 'slug')]

class CircuitTournament(models.Model):
    circuit = models.ForeignKey(Circuit, on_delete=models.CASCADE)
    tournament = models.ForeignKey('tournaments.Tournament', on_delete=models.CASCADE)
    weight = models.FloatField(default=1.0)  # Weighting for circuit standings
    order = models.IntegerField()
```

**Accessible at:** `dues.nekotab.app/circuits/national-circuit-2026/`

### 11.5 Global Rankings

Cross-organization rankings require a separate system:

- **Rankings app** (`rankings/`) operates at the platform level (not org-scoped)
- Aggregates debater performance across all participating organizations
- Requires debater passport opt-in
- Organization workspace provides the data pipeline: org → tournaments → passport → rankings

### 11.6 Performance at Scale

| Concern | Mitigation |
|---------|-----------|
| Tenant resolution on every request | Two-tier cache (Redis): `tenant_type_{label}` + `org_obj_{label}`. Hot path is a single cache GET. |
| Organization with 100+ tournaments | `Tournament.objects.filter(organization=org, active=True)` is indexed. Dashboard uses `select_related` / `prefetch_related`. |
| Shared judge pool with 1000+ judges | Paginated list view. Import-into-tournament is a background task (Celery/Django-Q). |
| Slug reservation locking | `select_for_update()` on `SubdomainSlugReservation` during creation; contention is negligible (creation is rare). |
| Per-request URL config swap | `request.urlconf` is a built-in Django mechanism, zero overhead beyond the initial assignment. URL resolution is re-run with the new config, which Django handles natively. |

---

## Appendix A — Settings Changes

```python
# settings/core.py — changes

MIDDLEWARE = [
    # ... unchanged through AuthenticationMiddleware ...
    # OLD: 'utils.middleware.SubdomainTournamentMiddleware',
    'utils.middleware.SubdomainTenantMiddleware',   # NEW — replaces old middleware
    'utils.middleware.DebateMiddleware',             # unchanged
    # ... rest unchanged ...
]

# New setting
ORGANIZATION_WORKSPACES_ENABLED = _env_bool('ORGANIZATION_WORKSPACES_ENABLED', default=False)
```

## Appendix B — Signal Additions

```python
# organizations/signals.py — additions

from tournaments.models import Tournament
from core.models import SubdomainSlugReservation

@receiver(post_save, sender=Organization)
def invalidate_org_tenant_cache(sender, instance, **kwargs):
    """Clear tenant resolution cache when an org is created/modified."""
    cache.delete(f"tenant_type_{instance.slug}")
    cache.delete(f"org_obj_{instance.slug}")

@receiver(post_delete, sender=Organization)
def invalidate_org_tenant_cache_on_delete(sender, instance, **kwargs):
    cache.delete(f"tenant_type_{instance.slug}")
    cache.delete(f"org_obj_{instance.slug}")

@receiver(post_save, sender=Tournament)
def invalidate_tournament_tenant_cache(sender, instance, **kwargs):
    cache.delete(f"tenant_type_{instance.slug}")
    cache.delete(f"subdom_tour_exists_{instance.slug}")

@receiver(post_delete, sender=Tournament)
def invalidate_tournament_tenant_cache_on_delete(sender, instance, **kwargs):
    cache.delete(f"tenant_type_{instance.slug}")
    cache.delete(f"subdom_tour_exists_{instance.slug}")
```

## Appendix C — Migration File Summary

| Migration | App | Action |
|-----------|-----|--------|
| `0002_add_workspace_fields` | `organizations` | Add `is_workspace_enabled`, `description`, `logo` to `Organization` |
| `0002_add_tabmaster_editor_roles` | `organizations` | Extend `Role` choices (backward-compatible, just new options) |
| `0001_initial` | `core` | Create `SubdomainSlugReservation` model |
| `0002_backfill_slug_reservations` | `core` | Data migration: create reservation rows for all existing tournaments |
| `00XX_add_org_slug_index` | `tournaments` | Add composite index `(organization, slug)` and `(organization, active)` |
