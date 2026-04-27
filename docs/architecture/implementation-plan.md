# Organization Workspace — Implementation Plan

**System:** NekoTab v2.10.x (Django 5.2, PostgreSQL, Redis)  
**Reference:** [organization-workspace-blueprint.md](organization-workspace-blueprint.md)  
**Date:** 2026-03-06

---

## Current State Inventory

All paths below are relative to `tabbycat/`.

| Asset | Current State |
|-------|--------------|
| `organizations/models.py` | `Organization` (name, slug, created_at, updated_at), `OrganizationMembership` (4 roles: owner/admin/member/viewer) |
| `organizations/migrations/` | `0001_create_organization_models.py` |
| `tournaments/models.py` | `Tournament.organization` FK (non-null, PROTECT), `Tournament.slug` globally unique |
| `tournaments/migrations/` | Through `0039_enforce_organization_not_null.py` |
| `utils/middleware.py` | `SubdomainTournamentMiddleware` (tournament-only lookup), `DebateMiddleware` |
| `tournaments/signals.py` | Cache invalidation for `subdom_tour_exists_*` keys |
| `organizations/signals.py` | Permission cache versioning, tournament object cache invalidation |
| `users/permissions.py` | `has_permission()` with org OWNER/ADMIN short-circuit, MEMBER pass-through |
| `settings/core.py` | `SUBDOMAIN_TOURNAMENTS_ENABLED`, `SUBDOMAIN_BASE_DOMAIN`, `RESERVED_SUBDOMAINS` |
| `core/` app | **Does not exist** — must be created |
| `organizations/workspace_urls.py` | **Does not exist** |
| `organizations/workspace_views.py` | **Does not exist** |
| `organizations/workspace_mixins.py` | **Does not exist** |
| `organizations/forms.py` | **Does not exist** |
| `organizations/permissions.py` | **Does not exist** |
| `templates/organizations/workspace/` | **Does not exist** |
| `templates/marketing/` | **Does not exist** |

---

## Phase 1 — Foundation Models

### Purpose

Add the `is_workspace_enabled`, `description`, and `logo` fields to `Organization`. Extend `OrganizationMembership.Role` with `tabmaster` and `editor`. These are purely additive schema changes — no routing, middleware, or view changes.

### Files to Modify

| File | Change |
|------|--------|
| `organizations/models.py` | Add 3 fields to `Organization`, add 2 role choices to `OrganizationMembership.Role`, update `ROLE_HIERARCHY` |
| `organizations/admin.py` | Add `is_workspace_enabled` to `list_display` and `list_filter` |
| `organizations/tests.py` | Add tests for new fields and new role levels |

### No New Files

All changes are to existing files.

### Migration

**File:** `organizations/migrations/0002_add_workspace_fields.py`

```
python manage.py makemigrations organizations --name add_workspace_fields
```

This generates a single migration containing:

1. `AddField('organization', 'is_workspace_enabled', BooleanField(default=False, db_index=True))`
2. `AddField('organization', 'description', TextField(blank=True, default=''))`
3. `AddField('organization', 'logo', ImageField(upload_to='org_logos/', blank=True, null=True))`
4. `AlterField('organizationmembership', 'role', ...)` — extends choices to include `tabmaster` and `editor`

### Code-Level Tasks

**1. `organizations/models.py` — Organization class, after `updated_at`:**

```python
is_workspace_enabled = models.BooleanField(
    default=False,
    db_index=True,
    verbose_name=_("workspace enabled"),
    help_text=_("When enabled, this organization is accessible via its own subdomain."),
)
description = models.TextField(
    blank=True, default="",
    verbose_name=_("description"),
)
logo = models.ImageField(
    upload_to='org_logos/', blank=True, null=True,
    verbose_name=_("logo"),
)
```

**2. `organizations/models.py` — OrganizationMembership.Role, add between ADMIN and MEMBER:**

```python
class Role(models.TextChoices):
    OWNER     = 'owner',     _("Owner")
    ADMIN     = 'admin',     _("Admin")
    TABMASTER = 'tabmaster', _("Tabmaster")
    EDITOR    = 'editor',    _("Editor")
    VIEWER    = 'viewer',    _("Viewer")
    # 'member' kept as alias for backward compat with existing DB rows
    MEMBER    = 'member',    _("Member")
```

**Critical:** Existing rows in the database have `role='member'`. This value must remain valid. We keep `MEMBER` in the choices and treat it as equivalent to `EDITOR` in the hierarchy. The `ROLE_HIERARCHY` becomes:

```python
ROLE_HIERARCHY = {
    Role.OWNER:     5,
    Role.ADMIN:     4,
    Role.TABMASTER: 3,
    Role.EDITOR:    2,
    Role.MEMBER:    2,   # legacy alias — same level as EDITOR
    Role.VIEWER:    1,
}
```

**3. `organizations/admin.py` — OrganizationAdmin.list_display:**

Add `'is_workspace_enabled'` to `list_display`. Add `'is_workspace_enabled'` to `list_filter`.

**4. `organizations/models.py` — update `user_is_org_admin()` helper:**

Add `'tabmaster'` to the role check list if the function is used for tournament-admin-level access. Currently it checks `[OWNER, ADMIN]` which is correct — no change needed unless Tabmaster should count as "admin." For now, **do not change** — Tabmaster access is handled separately in Phase 9.

### Backward Compatibility

- `default=False` on `is_workspace_enabled` means all existing orgs remain backend-only. No routing behavior changes.
- Existing `role='member'` rows remain valid because `MEMBER` stays in the choices.
- No middleware changes. No URL changes. No view changes.

### Testing

```bash
python manage.py test organizations.tests -v2
```

Write tests:
- `test_new_org_defaults_workspace_disabled` — Create an org, assert `is_workspace_enabled` is `False`
- `test_tabmaster_role_level` — Create membership with `role='tabmaster'`, assert `role_level == 3`
- `test_editor_role_level` — Assert `role_level == 2`
- `test_member_role_still_valid` — Assert existing `role='member'` rows still work
- `test_has_role_at_least_hierarchy` — Tabmaster >= Editor, Tabmaster < Admin, etc.

### Rollback Strategy

```bash
python manage.py migrate organizations 0001_create_organization_models
```

This reverts all three new fields and the role change. Safe because no data depends on the new fields yet.

---

## Phase 2 — Subdomain Slug Reservation

### Purpose

Create a cross-entity slug registry (`SubdomainSlugReservation`) that guarantees no tournament slug collides with an organization workspace slug. This is a safety net that must be in place before the middleware upgrade.

### New Files to Create

| File | Purpose |
|------|---------|
| `core/__init__.py` | Empty file, creates the `core` app |
| `core/apps.py` | AppConfig for `core` |
| `core/models.py` | `SubdomainSlugReservation` model |
| `core/admin.py` | Admin interface for slug reservations |
| `core/migrations/__init__.py` | Empty |
| `core/migrations/0001_initial.py` | Auto-generated |
| `core/migrations/0002_backfill_tournament_slugs.py` | Data migration |

### Files to Modify

| File | Change |
|------|--------|
| `settings/core.py` | Add `'core'` to `TABBYCAT_APPS` (before `'organizations'`) |
| `tournaments/signals.py` | Add `SubdomainSlugReservation` create/delete in tournament post_save/post_delete |
| `organizations/signals.py` | Add `SubdomainSlugReservation` create/delete in org post_save/post_delete (only when `is_workspace_enabled`) |
| `tournaments/models.py` | Add `clean()` method to check slug not in org workspace slugs |
| `organizations/models.py` | Add `clean()` method to check slug not in tournament slugs |

### Code-Level Tasks

**1. `core/models.py`:**

```python
from django.db import models
from django.utils.translation import gettext_lazy as _
from tournaments.validators import validate_dns_safe_slug


class SubdomainSlugReservation(models.Model):
    TENANT_TYPES = [
        ('tournament', 'Tournament'),
        ('organization', 'Organization'),
    ]

    slug = models.SlugField(
        unique=True,
        max_length=80,
        validators=[validate_dns_safe_slug],
        verbose_name=_("slug"),
    )
    tenant_type = models.CharField(max_length=20, choices=TENANT_TYPES)
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
        verbose_name = _("subdomain slug reservation")
        verbose_name_plural = _("subdomain slug reservations")

    def __str__(self):
        return f"{self.slug} ({self.tenant_type})"
```

**2. `core/apps.py`:**

```python
from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Core'
```

**3. `settings/core.py` — add `'core'` to TABBYCAT_APPS:**

Insert `'core',` as the **first** entry in `TABBYCAT_APPS` (before `'actionlog'`).

**4. Data migration `core/migrations/0002_backfill_tournament_slugs.py`:**

```python
from django.db import migrations

def backfill(apps, schema_editor):
    Tournament = apps.get_model('tournaments', 'Tournament')
    SubdomainSlugReservation = apps.get_model('core', 'SubdomainSlugReservation')
    for t in Tournament.objects.all():
        SubdomainSlugReservation.objects.get_or_create(
            slug=t.slug.lower(),
            defaults={
                'tenant_type': 'tournament',
                'tournament': t,
                'organization': None,
            }
        )

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
        ('tournaments', '0039_enforce_organization_not_null'),
    ]
    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
```

**5. `tournaments/signals.py` — add reservation sync:**

After the existing `update_tournament_cache` signal handler, add:

```python
@receiver(post_save, sender=Tournament)
def sync_slug_reservation_on_save(sender, instance, created, **kwargs):
    if created:
        from core.models import SubdomainSlugReservation
        SubdomainSlugReservation.objects.get_or_create(
            slug=instance.slug.lower(),
            defaults={
                'tenant_type': 'tournament',
                'tournament': instance,
            }
        )
```

On tournament delete, `CASCADE` on the FK handles cleanup automatically.

**6. `tournaments/models.py` — add `clean()` to Tournament:**

```python
def clean(self):
    super().clean()
    from organizations.models import Organization
    if Organization.objects.filter(
        slug__iexact=self.slug, is_workspace_enabled=True
    ).exists():
        from django.core.exceptions import ValidationError
        raise ValidationError({
            'slug': _("This slug is already in use by an organization workspace."),
        })
```

**7. `organizations/models.py` — add `clean()` to Organization:**

```python
def clean(self):
    super().clean()
    if self.is_workspace_enabled:
        from tournaments.models import Tournament
        if Tournament.objects.filter(slug__iexact=self.slug).exists():
            from django.core.exceptions import ValidationError
            raise ValidationError({
                'slug': _("This slug is already in use by a tournament."),
            })
```

### Migrations

```bash
python manage.py makemigrations core --name initial
python manage.py migrate core 0001
python manage.py migrate core 0002
```

### Backward Compatibility

- The `core` app is pure infrastructure — no views, no URLs, no middleware.
- The data migration is read-only from `tournaments` perspective (only creates new rows in a new table).
- Tournament `clean()` only blocks creation when a workspace org has the same slug. Since `is_workspace_enabled=False` for all existing orgs, this is a no-op for current data.
- All existing tournament creation flows call `form.save()` which triggers `clean()` via `full_clean()` in ModelForm. Manual `.save()` calls bypass `clean()` — this is acceptable as a secondary safety layer (the slug reservation table is the primary).

### Testing

```bash
python manage.py test core -v2
```

Write tests in `core/tests.py`:
- `test_backfill_creates_reservations` — Assert every tournament has a corresponding reservation
- `test_duplicate_slug_blocked` — Create a tournament, try to create an org with same slug + `is_workspace_enabled=True`, assert `ValidationError`
- `test_reservation_cascade_on_tournament_delete` — Delete tournament, assert reservation gone
- `test_reservation_created_on_tournament_create` — Create tournament via signal, assert reservation exists
- `test_check_constraint_rejects_both_fks` — Try to create reservation with both tournament and organization set, assert `IntegrityError`

### Rollback Strategy

```bash
python manage.py migrate core zero
```

Then remove `'core'` from `TABBYCAT_APPS`. Remove signal additions from `tournaments/signals.py`. Remove `clean()` additions from both models. The `core/` directory can be left in place (dead code) or deleted.

---

## Phase 3 — Middleware Upgrade

### Purpose

Replace `SubdomainTournamentMiddleware` with `SubdomainTenantMiddleware` that resolves both tournament and organization tenants. This is the highest-risk phase — it touches every HTTP request.

### Files to Modify

| File | Change |
|------|--------|
| `utils/middleware.py` | Add `SubdomainTenantMiddleware` class (new code, ~150 lines). **Do not delete** `SubdomainTournamentMiddleware` yet. |
| `settings/core.py` | Add `ORGANIZATION_WORKSPACES_ENABLED` setting. Swap middleware class in `MIDDLEWARE` list. |
| `settings/digitalocean.py` | Add `ORGANIZATION_WORKSPACES_ENABLED` env var parsing |
| `utils/tests_subdomain.py` | Add tests for the new middleware |
| `organizations/signals.py` | Add tenant cache invalidation for org save/delete |

### No New Files

All changes are inline in existing files.

### Code-Level Tasks

**1. `settings/core.py` — add new setting after `RESERVED_SUBDOMAINS`:**

```python
# Organization workspace routing; when False, SubdomainTenantMiddleware
# behaves identically to the old SubdomainTournamentMiddleware.
ORGANIZATION_WORKSPACES_ENABLED = _env_bool('ORGANIZATION_WORKSPACES_ENABLED')
```

**2. `settings/core.py` — swap middleware in `MIDDLEWARE` list:**

Replace:
```python
'utils.middleware.SubdomainTournamentMiddleware',
```
With:
```python
'utils.middleware.SubdomainTenantMiddleware',
```

**3. `settings/digitalocean.py` — add after existing subdomain settings:**

```python
ORGANIZATION_WORKSPACES_ENABLED = environ.get('ORGANIZATION_WORKSPACES_ENABLED', 'false').lower() == 'true'
```

**4. `utils/middleware.py` — add `SubdomainTenantMiddleware`:**

Add the new class **after** the existing `SubdomainTournamentMiddleware` (which stays in the file for reference / rollback). Key implementation details:

```python
class SubdomainTenantMiddleware:
    """Resolves subdomain to Tournament or Organization workspace.

    Sets on request:
        request.tenant_type          — 'tournament' | 'organization' | None
        request.tenant_organization  — Organization instance or None
        request.subdomain_tournament — str slug or None (backward compat)
    """
```

**Resolution logic:**

```python
def _resolve_tenant(self, label):
    if not getattr(settings, 'ORGANIZATION_WORKSPACES_ENABLED', False):
        # Legacy mode: tournament-only
        if self._tournament_exists(label):
            return ('tournament', label)
        return (None, None)

    # Full mode: tournament-first, then organization
    if self._tournament_exists(label):
        return ('tournament', label)
    org = self._get_workspace_org(label)
    if org:
        return ('organization', org)
    return (None, None)
```

**For tournament tenants:** Identical rewriting logic to the existing `SubdomainTournamentMiddleware` — copy the path-rewriting code verbatim.

**For organization tenants:** Set `request.urlconf = 'organizations.workspace_urls'`. Do NOT rewrite `path_info`. (Note: `workspace_urls.py` doesn't exist yet; this code path won't be reached until `ORGANIZATION_WORKSPACES_ENABLED=True` and a workspace org exists.)

**Request attributes set on every request:**

```python
request.tenant_type = None
request.tenant_organization = None
request.subdomain_tournament = None  # backward compat
```

**5. `organizations/signals.py` — add tenant cache invalidation:**

Add after existing handlers:

```python
@receiver(post_save, sender=Organization)
def invalidate_tenant_cache_on_org_save(sender, instance, **kwargs):
    cache.delete(f"tenant_type_{instance.slug}")
    cache.delete(f"tenant_type_{instance.slug.lower()}")
    cache.delete(f"org_obj_{instance.slug}")
    cache.delete(f"org_obj_{instance.slug.lower()}")

@receiver(post_delete, sender=Organization)
def invalidate_tenant_cache_on_org_delete(sender, instance, **kwargs):
    cache.delete(f"tenant_type_{instance.slug}")
    cache.delete(f"tenant_type_{instance.slug.lower()}")
    cache.delete(f"org_obj_{instance.slug}")
    cache.delete(f"org_obj_{instance.slug.lower()}")
```

**6. `tournaments/signals.py` — add tenant cache key:**

In the existing `update_tournament_cache` and `clear_tournament_cache_on_delete` handlers, add:

```python
cache.delete("tenant_type_%s" % instance.slug)
cache.delete("tenant_type_%s" % instance.slug.lower())
```

### Migration

No database migration. This is a pure code change.

### Backward Compatibility

**This is the critical safety mechanism:** When `ORGANIZATION_WORKSPACES_ENABLED=False` (the default), the new middleware's `_resolve_tenant()` only performs tournament lookups. It sets the same `request.subdomain_tournament` attribute. The path-rewriting logic is identical. From the perspective of all downstream code (templates, `DebateMiddleware`, views, context processors), the behavior is indistinguishable from the old middleware.

**Verify this claim by running the existing subdomain test suite:**

```bash
python manage.py test utils.tests_subdomain -v2
```

These tests use `SubdomainTournamentMiddleware` by class name in imports. They must be updated to import `SubdomainTenantMiddleware` instead, or — safer — make them test the middleware that's actually in the `MIDDLEWARE` setting.

### Testing

**Existing tests must pass unchanged** (except import updates):

```bash
python manage.py test utils.tests_subdomain -v2
```

**New tests to add to `utils/tests_subdomain.py`:**

```python
# --- With ORGANIZATION_WORKSPACES_ENABLED=False (default) ---
test_org_workspace_disabled_ignores_org_subdomain
    # Create org with is_workspace_enabled=True
    # GET org-slug.nekotab.app/ → should 404 (not resolved as org)

# --- With ORGANIZATION_WORKSPACES_ENABLED=True ---
test_tournament_subdomain_still_works_when_org_enabled
    # GET test-tourney.nekotab.app/ → 200/302 (tournament resolves)

test_org_subdomain_resolves_when_enabled
    # Create org with is_workspace_enabled=True
    # GET org-slug.nekotab.app/ → should NOT 404
    # (will 404 on URL resolution because workspace_urls.py doesn't exist yet)
    # For now, assert request.tenant_type == 'organization'
    # Use RequestFactory + middleware.__call__ directly

test_tournament_takes_priority_over_org
    # Create tournament slug='collision'
    # Create org slug='collision', is_workspace_enabled=True
    # (would fail clean() — so use .objects.create to bypass)
    # GET collision.nekotab.app/ → resolves as tournament, not org

test_request_attributes_set_correctly_tournament
    # Assert request.tenant_type == 'tournament'
    # Assert request.subdomain_tournament == slug
    # Assert request.tenant_organization is None

test_request_attributes_set_correctly_organization
    # Assert request.tenant_type == 'organization'
    # Assert request.subdomain_tournament is None
    # Assert request.tenant_organization == org

test_negative_cache_short_ttl
    # Verify unknown subdomain gets cached with short TTL
```

**Integration smoke test (manual):**

```bash
# Local development with SUBDOMAIN_TOURNAMENTS_ENABLED=True
# 1. Create a tournament with slug='test-tourney'
# 2. curl -H "Host: test-tourney.nekotab.app" http://localhost:8000/
#    → Should return tournament page (200/302)
# 3. curl -H "Host: nonexistent.nekotab.app" http://localhost:8000/
#    → Should return 404
```

### Rollback Strategy

**Immediate (no deploy):** Set `ORGANIZATION_WORKSPACES_ENABLED=False` in environment. Middleware reverts to tournament-only mode.

**Full rollback (deploy):** In `settings/core.py`, swap middleware back:

```python
# Revert to:
'utils.middleware.SubdomainTournamentMiddleware',
```

The old class remains in `utils/middleware.py` untouched, so this is a one-line config change.

---

## Phase 4 — Organization Workspace URLs

### Purpose

Create the URL namespace that Django uses when `request.urlconf = 'organizations.workspace_urls'` is set by the tenant middleware. This phase creates the URL routing skeleton and placeholder views. No public-facing UI yet.

### New Files to Create

| File | Purpose |
|------|---------|
| `organizations/workspace_urls.py` | Root URL config for org subdomains |
| `organizations/workspace_views.py` | Stub views returning minimal responses |
| `organizations/workspace_mixins.py` | Access control mixins for workspace views |

### Files to Modify

| File | Change |
|------|--------|
| `utils/middleware.py` | In `DebateMiddleware.process_view()`, add cross-tenant isolation check |
| `utils/context_processors.py` | Pass `workspace_org` / `workspace_url` to template context when org tenant detected |

### Code-Level Tasks

**1. `organizations/workspace_urls.py`:**

```python
from django.urls import include, path
from django.views.i18n import JavaScriptCatalog

from . import workspace_views

app_name = 'workspace'

urlpatterns = [
    # Workspace pages
    path('', workspace_views.WorkspaceDashboardView.as_view(), name='dashboard'),
    path('tournaments/', workspace_views.TournamentListView.as_view(), name='tournament-list'),
    path('tournaments/new/', workspace_views.TournamentCreateView.as_view(), name='tournament-create'),
    path('members/', workspace_views.MembersView.as_view(), name='members'),
    path('settings/', workspace_views.SettingsView.as_view(), name='settings'),
    path('archive/', workspace_views.ArchiveView.as_view(), name='archive'),

    # Nested tournament access — delegates to existing tournament URL patterns
    path('tournaments/<slug:tournament_slug>/', include('tournaments.urls')),

    # System routes that must work on org subdomains
    path('accounts/', include('users.urls')),
    path('i18n/', include('django.conf.urls.i18n')),
    path('jsi18n/', JavaScriptCatalog.as_view(domain="djangojs"), name='javascript-catalog'),
    path('api/', include('api.urls')),

    # Static file prefixes handled by WhiteNoise (no URL pattern needed),
    # but the following ensure Django admin / summernote still work if accessed
    path('database/', include('utils.admin_site_urls')),  # or admin.site.urls
    path('jet/', include('jet.urls', 'jet')),
    path('summernote/', include('django_summernote.urls')),
]
```

**Important:** The `path('tournaments/<slug:tournament_slug>/', include('tournaments.urls'))` line is what allows `dues.nekotab.app/tournaments/novice-open/admin/draw/` to work. It feeds into the existing tournament URL patterns, which `DebateMiddleware` resolves.

**2. `organizations/workspace_mixins.py`:**

```python
from django.contrib.auth.views import redirect_to_login
from django.http import Http404, HttpResponseForbidden

from .models import OrganizationMembership


class WorkspaceAccessMixin:
    """Requires authenticated user + membership in the tenant organization."""

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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['organization'] = self.organization
        ctx['membership'] = self.membership
        return ctx


class WorkspaceAdminMixin(WorkspaceAccessMixin):
    """Requires ADMIN or OWNER role in the organization."""

    def dispatch(self, request, *args, **kwargs):
        resp = super().dispatch(request, *args, **kwargs)
        if hasattr(self, 'membership') and self.membership:
            if not self.membership.has_role_at_least(OrganizationMembership.Role.ADMIN):
                return HttpResponseForbidden("Admin access required.")
        return resp


class WorkspaceOwnerMixin(WorkspaceAccessMixin):
    """Requires OWNER role."""

    def dispatch(self, request, *args, **kwargs):
        resp = super().dispatch(request, *args, **kwargs)
        if hasattr(self, 'membership') and self.membership:
            if self.membership.role != OrganizationMembership.Role.OWNER:
                return HttpResponseForbidden("Owner access required.")
        return resp
```

**3. `organizations/workspace_views.py` — stub views:**

```python
from django.http import JsonResponse
from django.views.generic import TemplateView

from .workspace_mixins import WorkspaceAccessMixin, WorkspaceAdminMixin


class WorkspaceDashboardView(WorkspaceAccessMixin, TemplateView):
    template_name = 'organizations/workspace/dashboard.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab'] = 'dashboard'
        ctx['active_tournaments'] = self.organization.tournaments.filter(active=True)
        return ctx


class TournamentListView(WorkspaceAccessMixin, TemplateView):
    template_name = 'organizations/workspace/tournament_list.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab'] = 'tournaments'
        ctx['tournaments'] = self.organization.tournaments.all().order_by('-created_at')
        return ctx


class TournamentCreateView(WorkspaceAdminMixin, TemplateView):
    template_name = 'organizations/workspace/tournament_create.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab'] = 'tournaments'
        return ctx


class MembersView(WorkspaceAccessMixin, TemplateView):
    template_name = 'organizations/workspace/members.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab'] = 'members'
        ctx['members'] = self.organization.memberships.select_related('user').order_by('role')
        return ctx


class SettingsView(WorkspaceAdminMixin, TemplateView):
    template_name = 'organizations/workspace/settings.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab'] = 'settings'
        return ctx


class ArchiveView(WorkspaceAccessMixin, TemplateView):
    template_name = 'organizations/workspace/archive.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_tab'] = 'archive'
        ctx['archived_tournaments'] = self.organization.tournaments.filter(active=False)
        return ctx
```

**4. `utils/middleware.py` — DebateMiddleware cross-tenant check:**

In `DebateMiddleware.process_view()`, after the line `request.tournament = tournament` (or `request.tournament = cached_tournament`), add:

```python
# Cross-tenant isolation: if this request is on an org subdomain,
# the tournament must belong to that organization.
tenant_org = getattr(request, 'tenant_organization', None)
if tenant_org and request.tournament.organization_id != tenant_org.pk:
    return self._tournament_not_found_response(slug, request)
```

**5. `utils/context_processors.py` — extend `debate_context()`:**

At the end of the function (before `return context`), add:

```python
# Organization workspace context
tenant_org = getattr(request, 'tenant_organization', None)
if tenant_org:
    base = getattr(settings, 'SUBDOMAIN_BASE_DOMAIN', '')
    context['workspace_org'] = tenant_org
    context['workspace_url'] = f"https://{tenant_org.slug}.{base}/"
```

### Migration

No database migration.

### Backward Compatibility

- `workspace_urls.py` is only loaded when `request.urlconf` is set to it, which only happens when the middleware resolves an organization tenant. With `ORGANIZATION_WORKSPACES_ENABLED=False`, this code is never reached.
- The `DebateMiddleware` cross-tenant check uses `getattr(request, 'tenant_organization', None)` which returns `None` for all tournament-mode requests, so the check is a no-op.
- The context processor addition only fires when `tenant_organization` is set.

### Testing

```bash
python manage.py test organizations -v2
python manage.py test utils.tests_subdomain -v2
```

New tests for workspace URL resolution:

```python
# In organizations/tests.py or a new organizations/tests_workspace.py

@override_settings(ORGANIZATION_WORKSPACES_ENABLED=True, ...)
class WorkspaceURLTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(
            name='Test Org', slug='test-org', is_workspace_enabled=True)
        self.user = User.objects.create_user('testuser', password='password')
        OrganizationMembership.objects.create(
            organization=self.org, user=self.user, role='owner')

    def test_workspace_dashboard_requires_login(self):
        response = self.client.get('/', HTTP_HOST='test-org.nekotab.app')
        self.assertEqual(response.status_code, 302)  # redirect to login

    def test_workspace_dashboard_accessible_to_member(self):
        self.client.login(username='testuser', password='password')
        response = self.client.get('/', HTTP_HOST='test-org.nekotab.app')
        self.assertEqual(response.status_code, 200)

    def test_cross_tenant_blocked(self):
        # Create tournament in a DIFFERENT org
        other_org = Organization.objects.create(name='Other', slug='other-org')
        t = Tournament.objects.create(
            name='X', slug='x-tourney', seq=1, organization=other_org)
        self.client.login(username='testuser', password='password')
        # Try to access other org's tournament via our workspace
        response = self.client.get(
            '/tournaments/x-tourney/', HTTP_HOST='test-org.nekotab.app')
        self.assertEqual(response.status_code, 404)
```

### Rollback Strategy

Delete the three new files (`workspace_urls.py`, `workspace_views.py`, `workspace_mixins.py`). Revert the two-line additions in `DebateMiddleware` and `debate_context()`. No database changes to undo.

---

## Phase 5 — Organization Dashboard UI

### Purpose

Build the HTML/CSS templates for the workspace interface: sidebar layout, dashboard, tournament list, members list, settings, and archive pages.

### New Files to Create

| File | Purpose |
|------|---------|
| `templates/organizations/workspace/base.html` | Workspace base layout with sidebar |
| `templates/organizations/workspace/dashboard.html` | Dashboard with tournament cards |
| `templates/organizations/workspace/tournament_list.html` | All tournaments table |
| `templates/organizations/workspace/tournament_create.html` | Create tournament form |
| `templates/organizations/workspace/members.html` | Member list and invite |
| `templates/organizations/workspace/settings.html` | Org settings form |
| `templates/organizations/workspace/archive.html` | Archived tournament list |
| `static/css/workspace.css` | Workspace-specific styles |

### Files to Modify

| File | Change |
|------|--------|
| `organizations/workspace_views.py` | Flesh out stub views with full context data |

### Code-Level Tasks

**1. `templates/organizations/workspace/base.html`:**

This template does **NOT** extend `base.html` (the tournament base template). It is a standalone layout because the workspace has a fundamentally different navigation structure (sidebar vs. tournament navbar).

Structure:
```
<!DOCTYPE html>
<html>
<head>
  <!-- Standard meta, CSS (Bootstrap 4 + workspace.css) -->
  {% load static i18n %}
</head>
<body>
  <div class="workspace-layout">
    <nav class="workspace-sidebar">
      {% include "organizations/workspace/_sidebar.html" %}
    </nav>
    <main class="workspace-main">
      <header class="workspace-header">
        {% include "organizations/workspace/_header.html" %}
      </header>
      <div class="workspace-content">
        {% block content %}{% endblock %}
      </div>
    </main>
  </div>
</body>
</html>
```

**2. Workspace sidebar partial** (`_sidebar.html`):

```html
<div class="sidebar-brand">
  {% if organization.logo %}
    <img src="{{ organization.logo.url }}" alt="" class="sidebar-logo">
  {% endif %}
  <span>{{ organization.name }}</span>
</div>
<ul class="sidebar-nav">
  <li class="{% if active_tab == 'dashboard' %}active{% endif %}">
    <a href="/">Dashboard</a>
  </li>
  <li class="{% if active_tab == 'tournaments' %}active{% endif %}">
    <a href="/tournaments/">Tournaments</a>
  </li>
  <li class="{% if active_tab == 'members' %}active{% endif %}">
    <a href="/members/">Members</a>
  </li>
  <li class="{% if active_tab == 'settings' %}active{% endif %}">
    <a href="/settings/">Settings</a>
  </li>
  <li class="{% if active_tab == 'archive' %}active{% endif %}">
    <a href="/archive/">Archive</a>
  </li>
</ul>
```

### Migration

No database migration.

### Backward Compatibility

These templates live in a new directory and are only loaded by workspace views. Zero impact on existing templates.

### Testing

Manual testing only (UI templates):

```bash
# With ORGANIZATION_WORKSPACES_ENABLED=True, a workspace org, and the user logged in:
# 1. Visit org-slug.nekotab.app/ → see dashboard
# 2. Visit org-slug.nekotab.app/tournaments/ → see tournament list
# 3. Visit org-slug.nekotab.app/members/ → see member list
# 4. Visit org-slug.nekotab.app/settings/ → see settings form
# 5. Visit org-slug.nekotab.app/archive/ → see archive
# 6. Visit org-slug.nekotab.app/ as anonymous → redirected to login
# 7. Visit org-slug.nekotab.app/ as non-member → 404
```

### Rollback Strategy

Delete the `templates/organizations/workspace/` directory and `static/css/workspace.css`. Views will crash on template load, but they're only reachable behind the feature flag.

---

## Phase 6 — Tournament Creation Inside Organization

### Purpose

Allow workspace admins to create new tournaments within their organization from the workspace UI. The tournament is automatically associated with the workspace organization.

### New Files to Create

| File | Purpose |
|------|---------|
| `organizations/forms.py` | `WorkspaceTournamentCreateForm` |

### Files to Modify

| File | Change |
|------|--------|
| `organizations/workspace_views.py` | Replace stub `TournamentCreateView` with full `CreateView` implementation |
| `templates/organizations/workspace/tournament_create.html` | Wire up the form |

### Code-Level Tasks

**1. `organizations/forms.py`:**

```python
from django import forms
from django.utils.translation import gettext_lazy as _

from tournaments.models import Tournament


class WorkspaceTournamentCreateForm(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = ['name', 'short_name', 'slug']
        help_texts = {
            'slug': _("URL-safe identifier. Lowercase letters, numbers, and hyphens only."),
        }

    num_prelim_rounds = forms.IntegerField(
        min_value=1, initial=5,
        label=_("Number of preliminary rounds"),
    )

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization

    def clean_slug(self):
        slug = self.cleaned_data['slug'].lower()
        # Check global uniqueness (Tournament.slug is unique)
        if Tournament.objects.filter(slug__iexact=slug).exists():
            raise forms.ValidationError(_("This slug is already taken."))
        # Check against workspace org slugs
        from organizations.models import Organization
        if Organization.objects.filter(slug__iexact=slug, is_workspace_enabled=True).exists():
            raise forms.ValidationError(_("This slug is reserved."))
        return slug
```

**2. `organizations/workspace_views.py` — replace `TournamentCreateView`:**

```python
class TournamentCreateView(WorkspaceAdminMixin, CreateView):
    form_class = WorkspaceTournamentCreateForm
    template_name = 'organizations/workspace/tournament_create.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organization'] = self.organization
        return kwargs

    def form_valid(self, form):
        tournament = form.save(commit=False)
        tournament.organization = self.organization
        tournament.owner = self.request.user
        tournament.active = True
        tournament.save()
        # Create initial rounds
        from tournaments.utils import auto_make_rounds
        auto_make_rounds(tournament, form.cleaned_data['num_prelim_rounds'])
        # Redirect to tournament admin setup
        base = settings.SUBDOMAIN_BASE_DOMAIN
        return redirect(f"https://{self.organization.slug}.{base}/tournaments/{tournament.slug}/admin/")
```

### Migration

No database migration.

### Backward Compatibility

- This form is only accessible at `orgslug.nekotab.app/tournaments/new/` which requires workspace membership.
- The existing `CreateTournamentView` at `nekotab.app/create/` remains unchanged.
- Existing `Tournament.save()` triggers the signal that creates `SubdomainSlugReservation`.

### Testing

```python
# In organizations/tests_workspace.py
def test_create_tournament_in_workspace(self):
    self.client.login(username='admin_user', password='password')
    response = self.client.post('/tournaments/new/', {
        'name': 'New Open', 'short_name': 'NO', 'slug': 'new-open',
        'num_prelim_rounds': 5,
    }, HTTP_HOST='test-org.nekotab.app')
    self.assertEqual(response.status_code, 302)
    self.assertTrue(Tournament.objects.filter(slug='new-open').exists())
    t = Tournament.objects.get(slug='new-open')
    self.assertEqual(t.organization, self.org)

def test_viewer_cannot_create_tournament(self):
    # User with VIEWER role
    self.client.login(username='viewer_user', password='password')
    response = self.client.get('/tournaments/new/', HTTP_HOST='test-org.nekotab.app')
    self.assertEqual(response.status_code, 403)
```

### Rollback Strategy

Revert `workspace_views.py` to stub. Delete `forms.py`. The form is only reachable behind the workspace feature flag.

---

## Phase 7 — Registration Flows

### Purpose

Add two separate onboarding paths on the bare domain (`nekotab.app`): one for single-tournament creation and one for organization workspace creation.

### New Files to Create

| File | Purpose |
|------|---------|
| `templates/registration/register_tournament.html` | Single tournament registration form |
| `templates/registration/register_organization.html` | Org workspace registration form |
| `templates/registration/register_org_confirm.html` | Confirmation before redirect |

### Files to Modify

| File | Change |
|------|--------|
| `urls.py` (root) | Add paths: `register/tournament/`, `register/organization/` |
| `organizations/views.py` | Add `RegisterOrganizationView` |
| `tournaments/views.py` | Add `RegisterTournamentView` (or reference existing `CreateTournamentView`) |
| `organizations/forms.py` | Add `OrganizationRegistrationForm` |

### Code-Level Tasks

**1. `urls.py` — add before the tournament catch-all (`<slug:tournament_slug>/`):**

```python
# Registration flows
path('register/tournament/',
    tournaments.views.RegisterTournamentView.as_view(),
    name='register-tournament'),
path('register/organization/',
    organizations_views.RegisterOrganizationView.as_view(),
    name='register-organization'),
```

Add import at top:
```python
from organizations import views as organizations_views
```

**2. `organizations/forms.py` — add `OrganizationRegistrationForm`:**

```python
class OrganizationRegistrationForm(forms.ModelForm):
    class Meta:
        model = Organization
        fields = ['name', 'slug', 'description']

    def clean_slug(self):
        slug = self.cleaned_data['slug'].lower()
        if Organization.objects.filter(slug__iexact=slug).exists():
            raise forms.ValidationError(_("This slug is already taken."))
        if Tournament.objects.filter(slug__iexact=slug).exists():
            raise forms.ValidationError(_("This slug is reserved."))
        from core.models import SubdomainSlugReservation
        if SubdomainSlugReservation.objects.filter(slug__iexact=slug).exists():
            raise forms.ValidationError(_("This slug is already in use."))
        # Check reserved subdomains
        reserved = getattr(settings, 'RESERVED_SUBDOMAINS', [])
        if slug in reserved:
            raise forms.ValidationError(_("This slug is reserved."))
        return slug
```

**3. `organizations/views.py` — add `RegisterOrganizationView`:**

```python
class RegisterOrganizationView(LoginRequiredMixin, CreateView):
    form_class = OrganizationRegistrationForm
    template_name = 'registration/register_organization.html'

    def form_valid(self, form):
        from django.db import transaction
        from core.models import SubdomainSlugReservation

        with transaction.atomic():
            org = form.save(commit=False)
            org.is_workspace_enabled = True
            org.save()
            OrganizationMembership.objects.create(
                organization=org,
                user=self.request.user,
                role=OrganizationMembership.Role.OWNER,
            )
            SubdomainSlugReservation.objects.create(
                slug=org.slug.lower(),
                tenant_type='organization',
                organization=org,
            )

        base = getattr(settings, 'SUBDOMAIN_BASE_DOMAIN', 'nekotab.app')
        return redirect(f"https://{org.slug}.{base}/tournaments/new/")
```

**4. `tournaments/views.py` — add `RegisterTournamentView`:**

This is a streamlined version of the existing `CreateTournamentView`. The key difference: it auto-creates a backend-only `Organization` with `is_workspace_enabled=False`.

```python
class RegisterTournamentView(LoginRequiredMixin, CreateView):
    model = Tournament
    form_class = TournamentStartForm
    template_name = 'registration/register_tournament.html'

    def form_valid(self, form):
        from django.db import transaction
        from organizations.models import Organization, OrganizationMembership
        from core.models import SubdomainSlugReservation

        with transaction.atomic():
            # Auto-create phantom org
            org = Organization.objects.create(
                name=form.cleaned_data['name'],
                slug=form.cleaned_data['slug'],
                is_workspace_enabled=False,
            )
            OrganizationMembership.objects.create(
                organization=org,
                user=self.request.user,
                role=OrganizationMembership.Role.OWNER,
            )
            tournament = form.save(commit=False)
            tournament.organization = org
            tournament.owner = self.request.user
            tournament.save()
            # Rounds
            auto_make_rounds(tournament, form.cleaned_data['num_prelim_rounds'])
            # Slug reservation (also created by signal, but explicit for safety)
            SubdomainSlugReservation.objects.get_or_create(
                slug=tournament.slug.lower(),
                defaults={
                    'tenant_type': 'tournament',
                    'tournament': tournament,
                }
            )

        base = getattr(settings, 'SUBDOMAIN_BASE_DOMAIN', 'nekotab.app')
        if getattr(settings, 'SUBDOMAIN_TOURNAMENTS_ENABLED', False) and base:
            return redirect(f"https://{tournament.slug}.{base}/admin/")
        return redirect(f"/{tournament.slug}/admin/")
```

### Migration

No database migration.

### Backward Compatibility

- New URL paths (`/register/tournament/`, `/register/organization/`) do not conflict with any existing paths.
- The existing `/create/` path continues to work unchanged.
- The `LoginRequiredMixin` ensures non-authenticated users are redirected to login first.

### Testing

```python
def test_register_tournament_creates_phantom_org(self):
    self.client.login(username='testuser', password='password')
    response = self.client.post('/register/tournament/', {
        'name': 'My Open', 'short_name': 'MO', 'slug': 'my-open',
        'num_prelim_rounds': 5,
    })
    self.assertEqual(response.status_code, 302)
    t = Tournament.objects.get(slug='my-open')
    self.assertFalse(t.organization.is_workspace_enabled)

def test_register_organization_creates_workspace(self):
    self.client.login(username='testuser', password='password')
    response = self.client.post('/register/organization/', {
        'name': 'My Debate Society', 'slug': 'my-debate',
        'description': '',
    })
    self.assertEqual(response.status_code, 302)
    org = Organization.objects.get(slug='my-debate')
    self.assertTrue(org.is_workspace_enabled)
    self.assertTrue(OrganizationMembership.objects.filter(
        organization=org, user=self.user, role='owner').exists())

def test_slug_collision_tournament_org(self):
    Tournament.objects.create(name='X', slug='collider', seq=1, organization=self.org)
    self.client.login(username='testuser', password='password')
    response = self.client.post('/register/organization/', {
        'name': 'Collider Org', 'slug': 'collider', 'description': '',
    })
    self.assertEqual(response.status_code, 200)  # re-renders form with error
    self.assertFalse(Organization.objects.filter(slug='collider').exists())
```

### Rollback Strategy

Remove the two paths from `urls.py`. Remove the view classes. Delete the three templates. The existing `/create/` flow is unaffected.

---

## Phase 8 — Marketing Page

### Purpose

Add the `/for-organizers/` page that helps tournament organizers choose between single-tournament mode and organization workspace mode.

### New Files to Create

| File | Purpose |
|------|---------|
| `templates/marketing/for_organizers.html` | Full marketing page |
| `static/css/marketing.css` | Page-specific styles |

### Files to Modify

| File | Change |
|------|--------|
| `urls.py` (root) | Add path for `/for-organizers/` |

### Code-Level Tasks

**1. `urls.py` — add before registration paths:**

```python
path('for-organizers/',
    TemplateView.as_view(template_name='marketing/for_organizers.html'),
    name='for-organizers'),
```

**2. `templates/marketing/for_organizers.html`:**

Standalone template (like `nekotab_home.html`). Sections:

1. **Hero** — "Run Debate Tournaments at Any Scale"
2. **Decision Cards** — Two side-by-side cards: "Single Tournament" → `/register/tournament/`, "Organization Workspace" → `/register/organization/`
3. **Comparison Table** — Feature matrix (tournaments, roles, shared judges, etc.)
4. **Workspace Walkthrough** — 5-step visual flow
5. **Use Cases** — Federation / University / Circuit / Training cards
6. **How It Works** — Horizontal flow diagram
7. **Final CTA** — Two buttons repeating the decision cards

### Migration

No database migration.

### Backward Compatibility

Zero impact — new URL path, new template, new CSS file. Nothing existing is modified except one line in `urls.py`.

### Testing

Manual visual QA:
- Visit `nekotab.app/for-organizers/` → page loads
- Click "Create Tournament" → navigates to `/register/tournament/`
- Click "Create Workspace" → navigates to `/register/organization/`
- Mobile responsive check

### Rollback Strategy

Remove the one path from `urls.py`. Delete template and CSS file.

---

## Phase 9 — Security Hardening

### Purpose

Add the organization-role-to-permission mapping, harden cross-tenant isolation, and ensure the new roles integrate correctly with the existing permission system.

### New Files to Create

| File | Purpose |
|------|---------|
| `organizations/permissions.py` | `ROLE_PERMISSIONS` mapping: role → set of `Permission` choices |

### Files to Modify

| File | Change |
|------|--------|
| `users/permissions.py` | Update `has_permission()` to resolve Tabmaster/Editor/Viewer roles against `ROLE_PERMISSIONS` |
| `utils/middleware.py` | Verify cross-tenant check in `DebateMiddleware` (added in Phase 4) handles edge cases |
| `organizations/workspace_mixins.py` | Add CSRF and session validation |

### Code-Level Tasks

**1. `organizations/permissions.py`:**

```python
from users.permissions import Permission

ROLE_PERMISSIONS = {
    'owner':     '__all__',
    'admin':     '__all__',
    'tabmaster': {
        Permission.VIEW_TEAMS, Permission.ADD_TEAMS,
        Permission.VIEW_DECODED_TEAMS,
        Permission.VIEW_ADJUDICATORS, Permission.ADD_ADJUDICATORS,
        Permission.VIEW_ROOMS, Permission.ADD_ROOMS,
        Permission.VIEW_INSTITUTIONS, Permission.ADD_INSTITUTIONS,
        Permission.VIEW_PARTICIPANTS,
        Permission.VIEW_PARTICIPANT_DECODED,
        Permission.VIEW_PARTICIPANT_CONTACT,
        Permission.VIEW_ROUNDAVAILABILITIES,
        Permission.EDIT_ROUNDAVAILABILITIES,
        Permission.VIEW_DEBATE, Permission.VIEW_ADMIN_DRAW,
        Permission.GENERATE_DEBATE, Permission.DELETE_DEBATE,
        Permission.EDIT_DEBATETEAMS,
        Permission.VIEW_DEBATEADJUDICATORS,
        Permission.EDIT_DEBATEADJUDICATORS,
        Permission.VIEW_ROOMALLOCATIONS,
        Permission.EDIT_ROOMALLOCATIONS,
        Permission.VIEW_BALLOTSUBMISSIONS,
        Permission.EDIT_BALLOTSUBMISSIONS,
        Permission.ADD_BALLOTSUBMISSIONS,
        Permission.MARK_BALLOTSUBMISSIONS,
        Permission.VIEW_RESULTS,
        Permission.VIEW_MOTION, Permission.EDIT_MOTION,
        Permission.RELEASE_DRAW, Permission.RELEASE_MOTION,
        Permission.VIEW_SETTINGS, Permission.EDIT_SETTINGS,
        Permission.EDIT_BREAK_CATEGORIES,
        Permission.GENERATE_BREAK,
        Permission.VIEW_BREAK, Permission.VIEW_BREAK_OVERVIEW,
        Permission.CONFIRM_ROUND, Permission.EDIT_ROUND,
        Permission.CREATE_ROUND, Permission.DELETE_ROUND,
        Permission.VIEW_FEEDBACK, Permission.EDIT_FEEDBACK_CONFIRM,
        Permission.VIEW_FEEDBACK_OVERVIEW,
        Permission.VIEW_CHECKIN, Permission.EDIT_PARTICIPANT_CHECKIN,
        Permission.SEND_EMAILS,
        Permission.VIEW_REGISTRATION,
        Permission.EDIT_QUESTIONS,
    },
    'editor': {
        Permission.VIEW_TEAMS, Permission.VIEW_ADJUDICATORS,
        Permission.VIEW_ROOMS, Permission.VIEW_INSTITUTIONS,
        Permission.VIEW_PARTICIPANTS,
        Permission.VIEW_ROUNDAVAILABILITIES,
        Permission.EDIT_ROUNDAVAILABILITIES,
        Permission.VIEW_DEBATE,
        Permission.VIEW_BALLOTSUBMISSIONS,
        Permission.EDIT_OLD_BALLOTSUBMISSIONS,
        Permission.ADD_BALLOTSUBMISSIONS,
        Permission.VIEW_NEW_BALLOTSUBMISSIONS,
        Permission.VIEW_RESULTS,
        Permission.VIEW_MOTION,
        Permission.VIEW_FEEDBACK, Permission.ADD_FEEDBACK,
        Permission.VIEW_CHECKIN,
        Permission.EDIT_PARTICIPANT_CHECKIN,
        Permission.VIEW_REGISTRATION,
    },
    'member': {  # legacy alias — same as editor
        Permission.VIEW_TEAMS, Permission.VIEW_ADJUDICATORS,
        Permission.VIEW_ROOMS, Permission.VIEW_INSTITUTIONS,
        Permission.VIEW_PARTICIPANTS,
        Permission.VIEW_ROUNDAVAILABILITIES,
        Permission.EDIT_ROUNDAVAILABILITIES,
        Permission.VIEW_DEBATE,
        Permission.VIEW_BALLOTSUBMISSIONS,
        Permission.EDIT_OLD_BALLOTSUBMISSIONS,
        Permission.ADD_BALLOTSUBMISSIONS,
        Permission.VIEW_NEW_BALLOTSUBMISSIONS,
        Permission.VIEW_RESULTS,
        Permission.VIEW_MOTION,
        Permission.VIEW_FEEDBACK, Permission.ADD_FEEDBACK,
        Permission.VIEW_CHECKIN,
        Permission.EDIT_PARTICIPANT_CHECKIN,
        Permission.VIEW_REGISTRATION,
    },
    'viewer': {
        Permission.VIEW_TEAMS, Permission.VIEW_ADJUDICATORS,
        Permission.VIEW_ROOMS, Permission.VIEW_INSTITUTIONS,
        Permission.VIEW_PARTICIPANTS,
        Permission.VIEW_ROUNDAVAILABILITIES,
        Permission.VIEW_DEBATE,
        Permission.VIEW_BALLOTSUBMISSIONS,
        Permission.VIEW_NEW_BALLOTSUBMISSIONS,
        Permission.VIEW_RESULTS,
        Permission.VIEW_MOTION,
        Permission.VIEW_FEEDBACK,
        Permission.VIEW_FEEDBACK_OVERVIEW,
        Permission.VIEW_BREAK, Permission.VIEW_BREAK_OVERVIEW,
        Permission.VIEW_CHECKIN,
        Permission.VIEW_REGISTRATION,
    },
}
```

**2. `users/permissions.py` — update `has_permission()` org block:**

Replace the current org-membership section (lines ~173-193) with:

```python
if hasattr(tournament, 'organization_id') and tournament.organization_id:
    from organizations.models import OrganizationMembership
    from organizations.permissions import ROLE_PERMISSIONS

    # Check cache first
    version = _get_perm_cache_version(user.pk)
    cache_key = PERM_CACHE_KEY % (user.pk, tournament.slug, f'org_role', version)
    cached_role = cache.get(cache_key)

    if cached_role is None:
        org_membership = OrganizationMembership.objects.filter(
            organization_id=tournament.organization_id,
            user=user,
        ).values_list('role', flat=True).first()
        cached_role = org_membership or '__none__'
        cache.set(cache_key, cached_role, 600)

    if cached_role != '__none__':
        role_perms = ROLE_PERMISSIONS.get(cached_role)
        if role_perms == '__all__':
            return True
        if isinstance(role_perms, set) and permission in role_perms:
            return True
        # Role doesn't grant this permission — fall through to
        # per-tournament UserPermission / Group checks below
```

**3. Cross-tenant edge cases in `DebateMiddleware` (verify / harden):**

Verify the check from Phase 4 handles:
- `request.tenant_organization` is `None` when tournament mode → check is skipped (correct)
- API routes under org subdomains (`orgslug.nekotab.app/api/...`) → must also enforce isolation
- WebSocket routes → not handled by middleware (Channels handles auth separately; document as known gap)

**4. Session and CSRF safety for cross-subdomain auth:**

Add to `settings/core.py`:

```python
# Ensure session cookie works across tournament and org subdomains
SESSION_COOKIE_DOMAIN = f".{os.environ.get('SUBDOMAIN_BASE_DOMAIN', '')}" if os.environ.get('SUBDOMAIN_BASE_DOMAIN') else None
CSRF_COOKIE_DOMAIN = SESSION_COOKIE_DOMAIN
```

**Note:** This may already be configured. Check existing settings. If not present, this is critical — without it, a user logged in at `nekotab.app` won't have a valid session at `orgslug.nekotab.app`.

### Migration

No database migration.

### Backward Compatibility

- The `has_permission()` change is strictly more granular. The existing short-circuit for OWNER/ADMIN is preserved (via `'__all__'`). The existing pass-through for MEMBER is now explicit (MEMBER gets the `editor` permission set). Behavior is identical for existing roles.
- The new Tabmaster/Editor/Viewer roles only apply to memberships that use those role values. No existing data changes.

### Testing

```bash
python manage.py test users.tests -v2
python manage.py test organizations.tests -v2
```

New permission tests:

```python
def test_tabmaster_can_generate_draw(self):
    OrganizationMembership.objects.create(
        organization=self.org, user=self.user, role='tabmaster')
    t = Tournament.objects.create(name='X', slug='x', seq=1, organization=self.org)
    self.assertTrue(has_permission(self.user, Permission.GENERATE_DEBATE, t))

def test_editor_cannot_generate_draw(self):
    OrganizationMembership.objects.create(
        organization=self.org, user=self.user, role='editor')
    t = Tournament.objects.create(name='X', slug='x', seq=1, organization=self.org)
    self.assertFalse(has_permission(self.user, Permission.GENERATE_DEBATE, t))

def test_viewer_cannot_edit_ballots(self):
    OrganizationMembership.objects.create(
        organization=self.org, user=self.user, role='viewer')
    t = Tournament.objects.create(name='X', slug='x', seq=1, organization=self.org)
    self.assertFalse(has_permission(self.user, Permission.EDIT_BALLOTSUBMISSIONS, t))

def test_legacy_member_role_still_grants_editor_perms(self):
    OrganizationMembership.objects.create(
        organization=self.org, user=self.user, role='member')
    t = Tournament.objects.create(name='X', slug='x', seq=1, organization=self.org)
    self.assertTrue(has_permission(self.user, Permission.ADD_BALLOTSUBMISSIONS, t))
```

### Rollback Strategy

Revert `users/permissions.py` to the pre-Phase-9 version (restore the simple OWNER/ADMIN short-circuit and MEMBER pass-through). Delete `organizations/permissions.py`. Existing behavior is fully restored.

---

## Phase 10 — Feature Flag Rollout

### Purpose

Enable `ORGANIZATION_WORKSPACES_ENABLED=True` in production. This is a deployment and monitoring phase, not a code phase.

### Files to Modify

| File | Change |
|------|--------|
| `settings/digitalocean.py` | Change default from `'false'` to `'true'` (or set via environment variable) |

### Deployment Steps

**1. Pre-deployment verification (staging):**

```bash
# On staging environment with ORGANIZATION_WORKSPACES_ENABLED=True
python manage.py test -v2                              # Full test suite passes
python manage.py check --deploy                        # Django deployment checklist
python manage.py shell -c "
from core.models import SubdomainSlugReservation
from tournaments.models import Tournament
assert SubdomainSlugReservation.objects.count() >= Tournament.objects.count()
print('Slug reservations OK')
"
```

**2. Staged rollout plan:**

| Step | Action | Verify |
|------|--------|--------|
| 1 | Set `ORGANIZATION_WORKSPACES_ENABLED=true` on staging | All existing tournament subdomains resolve correctly |
| 2 | Create test organization workspace on staging | `test-org.staging.nekotab.app/` loads dashboard |
| 3 | Create tournament inside workspace | Tournament admin loads at `test-org.staging.nekotab.app/tournaments/test/admin/` |
| 4 | Verify cross-tenant isolation | Attempting to access another org's tournament → 404 |
| 5 | Set `ORGANIZATION_WORKSPACES_ENABLED=true` in production | Monitor error rates for 1 hour |
| 6 | Test one production org creation | Create `test-org.nekotab.app`, verify, then delete |

**3. Monitoring checklist:**

- [ ] Error rate (Sentry) — no spike in 500s
- [ ] `SubdomainTenantMiddleware` cache hit rate — check Redis `tenant_type_*` keys
- [ ] Existing tournament subdomain response times — no latency increase
- [ ] Auth flows — login at `nekotab.app`, verify session works at `orgslug.nekotab.app`
- [ ] API endpoints — verify `/api/` works on both tenant types

**4. Communication:**

- Add `/for-organizers/` link to homepage navigation
- Add "Create Organization" option to user dashboard

### Rollback Strategy

**Instant (< 1 min):** Set `ORGANIZATION_WORKSPACES_ENABLED=false` in environment variables. The middleware immediately reverts to tournament-only mode. Existing org workspaces become unreachable (404) but no data is lost. Re-enable when the issue is fixed.

**Data note:** Organizations created during the rollout retain their data. When re-enabled, they become accessible again.

---

## Dependency Graph

```
Phase 1 ─── Foundation Models
   │
   ▼
Phase 2 ─── Slug Reservation
   │
   ▼
Phase 3 ─── Middleware Upgrade ◄─── HIGHEST RISK
   │
   ├──────────────────────────────┐
   ▼                              ▼
Phase 4 ─── Workspace URLs     Phase 7 ─── Registration Flows
   │                              │
   ▼                              │
Phase 5 ─── Dashboard UI         │
   │                              │
   ▼                              │
Phase 6 ─── Tournament Create    │
   │                              │
   ├──────────────────────────────┘
   │
   ▼
Phase 8 ─── Marketing Page
   │
   ▼
Phase 9 ─── Security Hardening
   │
   ▼
Phase 10 ── Feature Flag Rollout
```

**Parallelizable:** Phases 4+5+6 and Phase 7 can be developed in parallel after Phase 3 is merged. Phase 8 can be developed at any point (it's purely a template). Phase 9 should be done before Phase 10.

---

## Full File Inventory

### New Files (17 files)

| File | Phase |
|------|-------|
| `core/__init__.py` | 2 |
| `core/apps.py` | 2 |
| `core/models.py` | 2 |
| `core/admin.py` | 2 |
| `core/tests.py` | 2 |
| `core/migrations/__init__.py` | 2 |
| `core/migrations/0001_initial.py` | 2 |
| `core/migrations/0002_backfill_tournament_slugs.py` | 2 |
| `organizations/workspace_urls.py` | 4 |
| `organizations/workspace_views.py` | 4 |
| `organizations/workspace_mixins.py` | 4 |
| `organizations/forms.py` | 6 |
| `organizations/permissions.py` | 9 |
| `templates/organizations/workspace/base.html` (+ 6 child templates) | 5 |
| `templates/registration/register_tournament.html` | 7 |
| `templates/registration/register_organization.html` | 7 |
| `templates/marketing/for_organizers.html` | 8 |
| `static/css/workspace.css` | 5 |
| `static/css/marketing.css` | 8 |

### Modified Files (14 files)

| File | Phase(s) |
|------|----------|
| `organizations/models.py` | 1, 2 |
| `organizations/admin.py` | 1 |
| `organizations/views.py` | 7 |
| `organizations/signals.py` | 3 |
| `organizations/tests.py` | 1, 4, 6, 9 |
| `tournaments/models.py` | 2 |
| `tournaments/views.py` | 7 |
| `tournaments/signals.py` | 2, 3 |
| `users/permissions.py` | 9 |
| `utils/middleware.py` | 3, 4 |
| `utils/context_processors.py` | 4 |
| `utils/tests_subdomain.py` | 3, 4 |
| `settings/core.py` | 2, 3, 9 |
| `settings/digitalocean.py` | 3, 10 |
| `urls.py` (root) | 7, 8 |

### Database Migrations (3 migrations)

| Migration | Phase | Type |
|-----------|-------|------|
| `organizations/0002_add_workspace_fields.py` | 1 | Schema (additive) |
| `core/0001_initial.py` | 2 | Schema (new table) |
| `core/0002_backfill_tournament_slugs.py` | 2 | Data (insert-only) |

All migrations are **additive** — no columns are removed, no tables are dropped, no existing data is modified. Every migration has a safe reverse path.
