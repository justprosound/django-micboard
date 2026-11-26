---
title: "Multi-tenancy and MSP support"
description: "Deployment modes, the tenant model, and how visibility is decided."
type: explanation
audience: developer
---
django-micboard supports optional multi-tenancy for managed service providers (MSPs) and multi-campus deployments through the `micboard.multitenancy` module. To turn it on, see [Enable multi-tenancy](multitenancy-setup.md).

## Deployment modes

Three deployment modes are supported:

1. **Single-Site** (default) - No tenant isolation, monitoring groups only
2. **Multi-Site** - Basic site-level filtering using Django's sites framework
3. **MSP Mode** - Full organization and campus hierarchy with strict isolation


## Tenant models

### Organization

Top-level tenant entity for MSP deployments.

**Fields:**
- `name` - Organization name (unique)
- `slug` - URL-safe identifier
- `site` - Django Site FK
- `is_active` - Active status
- `subscription_tier` - 'basic', 'pro', 'enterprise'
- `max_devices` - Organization-owned wireless chassis limit (`null` = unlimited). The canonical
  chassis persistence service locks the organization and enforces this limit for new inventory and
  ownership transfers; locationless platform inventory is outside organization quotas.
- `logo` - Organization logo
- `primary_color` - Brand color (hex)

### Campus

Sub-organization unit for multi-campus deployments.

### OrganizationMembership

User access to organizations with role-based permissions.

**Roles:**
- `viewer` - Read-only access
- `operator` - Can modify device assignments
- `admin` - Full access except billing
- `owner` - Full access including billing


## Service Layer Integration

Every request-facing read asks one question, "which rows of this model may this user see",
through `visible_to`:

```python
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.locations.structure import Location
from micboard.services.shared.visibility import visible_to

chassis = visible_to(WirelessChassis, user=request.user).filter(
    status__in=("online", "degraded", "provisioning"),
)
locations = visible_to(Location, user=request.user).filter(is_active=True)
```

The result is an ordinary queryset, so it can be filtered or locked further. Seeing a row does
not authorize changing it: check the user's membership role before calling `update()` or
`delete()` on it. Do not replace the authenticated user with optional tenant identifiers.

### Who sees what

Visibility is the tenant boundary intersected with monitoring reach. Monitoring reach is what
the user's active monitoring groups cover through their locations (including every room of an
"all rooms" building), their RF channels, and their performer assignments.

| Deployment | User | Sees |
| --- | --- | --- |
| Single-site | Superuser | Every row |
| Single-site | Anyone else | Monitoring reach |
| Multi-site | Superuser | Every row in the current site |
| Multi-site | Anyone else | Monitoring reach in the current site |
| MSP | Superuser with `MICBOARD_ALLOW_CROSS_ORG_VIEW` | Every tenant (inside the current site in multi-site mode) |
| MSP | `admin` or `owner` membership, or a superuser without cross-organization view | That membership's whole organization or campus |
| MSP | `viewer` or `operator` membership | Monitoring reach inside that membership's organization or campus |

Each membership contributes on its own, so a user who administers one organization and views
another sees all of the first and only their monitoring reach in the second. Monitoring groups
never widen a tenant: a group that covers another organization's location grants nothing there.
Anonymous and inactive accounts see nothing, and in MSP mode so does a user with no active
membership.

Monitoring groups themselves have no tenant. A user sees the active groups they belong to,
while the group reaches a building the user can see. In MSP mode an `admin` or `owner` also
sees every active group that stays entirely inside the organizations and campuses they
administer, and the Django admin lists every active group that stays inside the user's tenant
boundary. A group that reaches into another tenant is listed only to its members, because
listing it would expose that tenant's locations, channels, and members. A superuser without
cross-organization view sees only the groups it belongs to.

A model with no reviewed tenant ownership path is invisible to restricted users in MSP mode. A
model that monitoring groups cannot reach (a manufacturer, for example) is narrowed only by
the tenant boundary.

The Django admin applies only the tenant and site boundary, through
`restrict_to_tenant_boundary`: staff read their whole tenant there, and membership roles decide
what they may change.

### Active memberships

A membership counts only while its row, its organization, and any campus it names are active,
the campus belongs to the organization, and, in multi-site mode, the organization belongs to the
current site. `micboard.services.shared.tenant_principal.active_memberships` is the one place
that query is written, and every tenant decision reads it.

## Managers & Querysets

### TenantOptimizedQuerySet

`TenantOptimizedQuerySet` supplies the tenant filters that visibility composes, and models
expose it directly through `as_manager()`:

```python
from micboard.models.base_managers import TenantOptimizedQuerySet

class MyModel(models.Model):
    # ... fields

    objects = TenantOptimizedQuerySet.as_manager()

queryset = MyModel.objects.for_site(site_id=1)
queryset = MyModel.objects.for_memberships([(organization_id, None)])
```

`for_site` is a no-op outside multi-site mode; `for_memberships` always applies the
organization and campus identifiers it is given. Both fail closed for a model without an
ownership path. Neither decides what a user may see; use `visible_to` for that.


## Middleware

### TenantMiddleware

Attaches organization context to requests:

```python
from micboard.services.shared.visibility import visible_to
# In any view
def my_view(request):
    org = request.organization  # Current organization or None
    campus_id = request.campus_id  # Current campus ID or None

    chassis = visible_to(WirelessChassis, user=request.user).filter(
    status__in=("online", "degraded", "provisioning"),
)
```

**Organization detection priority:**
1. Session (user switched org)
2. User's primary organization membership
3. Subdomain (if `MICBOARD_SUBDOMAIN_ROUTING=True`)

**Switching organizations:**

```python
# In a view
def switch_org(request, org_id):
    request.session['current_organization_id'] = org_id
    return redirect('dashboard')
```


## Security

- **Tenant isolation**: Enforced at service layer and manager level
- **Superuser override**: Configurable via `MICBOARD_ALLOW_CROSS_ORG_VIEW`
- **Session hijacking**: Organization and campus IDs from the session or a profile are honoured only while an active membership covers them
- **Subdomain routing**: Requires proper DNS and SSL configuration


## Where to look in the code

- `micboard/multitenancy/models.py`: `Organization`, `Campus`, `OrganizationMembership`
- `micboard/models/base_managers.py`: `TenantOptimizedQuerySet`
- `micboard/multitenancy/middleware.py`: `TenantMiddleware`
- `micboard/services/shared/visibility.py`: `visible_to` and `restrict_to_tenant_boundary`
