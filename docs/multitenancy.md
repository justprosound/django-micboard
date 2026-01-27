# Multi-Tenancy & MSP Support

Django Micboard provides optional multi-tenancy support for Managed Service Providers (MSP) and multi-campus deployments through the `micboard.multitenancy` module.

## Overview

Three deployment modes are supported:

1. **Single-Site** (default) - No tenant isolation, monitoring groups only
2. **Multi-Site** - Basic site-level filtering using Django's sites framework
3. **MSP Mode** - Full organization and campus hierarchy with strict isolation

## Quick Start

### Single-Site (Default)

No configuration needed. Works out of the box.

```python
# settings.py
MICBOARD_MULTI_SITE_MODE = False
MICBOARD_MSP_ENABLED = False
```

### Multi-Site Mode

Enable Django's sites framework for basic site filtering:

```python
# settings.py
INSTALLED_APPS = [
    'django.contrib.sites',
    'micboard',
    # ... other apps
]

SITE_ID = 1
MICBOARD_MULTI_SITE_MODE = True
```

```bash
python manage.py migrate sites
python manage.py makemigrations micboard
python manage.py migrate micboard
```

### MSP Mode (Full Multi-Tenancy)

Enable organization and campus models:

```python
# settings.py
INSTALLED_APPS = [
    'django.contrib.sites',
    'micboard',
    'micboard.multitenancy',  # Add this
    # ... other apps
]

SITE_ID = 1
MICBOARD_MULTI_SITE_MODE = True
MICBOARD_MSP_ENABLED = True
MICBOARD_SITE_ISOLATION = 'organization'

MIDDLEWARE = [
    # ... existing middleware
    'micboard.multitenancy.middleware.TenantMiddleware',  # Add after auth
]
```

```bash
python manage.py migrate sites
python manage.py makemigrations micboard_multitenancy
python manage.py migrate micboard_multitenancy
python manage.py makemigrations micboard
python manage.py migrate micboard
```

## Configuration

### Settings Reference

Import the multitenancy settings template:

```python
# settings.py
from micboard.settings.multitenancy import *
```

Or customize individual settings:

```python
# Enable/disable features
MICBOARD_MULTI_SITE_MODE = False
MICBOARD_MSP_ENABLED = False
MICBOARD_SITE_ISOLATION = 'none'  # 'none', 'site', 'organization', 'campus'

# Cross-org access
MICBOARD_ALLOW_CROSS_ORG_VIEW = True  # Superusers see all orgs
MICBOARD_ALLOW_ORG_SWITCHING = True   # Users can switch between orgs

# Optional: Subdomain routing
MICBOARD_SUBDOMAIN_ROUTING = False
MICBOARD_ROOT_DOMAIN = 'micboard.example.com'
```

## Models

### Organization

Top-level tenant entity for MSP deployments.

```python
from micboard.multitenancy.models import Organization

# Create organization
org = Organization.objects.create(
    name="University A",
    slug="university-a",
    site_id=1,
    subscription_tier='enterprise',
    max_devices=500
)
```

**Fields:**
- `name` - Organization name (unique)
- `slug` - URL-safe identifier
- `site` - Django Site FK
- `is_active` - Active status
- `subscription_tier` - 'basic', 'pro', 'enterprise'
- `max_devices` - Device limit (null = unlimited)
- `logo` - Organization logo
- `primary_color` - Brand color (hex)

### Campus

Sub-organization unit for multi-campus deployments.

```python
from micboard.multitenancy.models import Campus

# Create campus
campus = Campus.objects.create(
    organization=org,
    name="North Campus",
    slug="north",
    address="123 University Ave",
    city="Boston",
    state="MA",
    timezone='America/New_York'
)
```

### OrganizationMembership

User access to organizations with role-based permissions.

```python
from micboard.multitenancy.models import OrganizationMembership

# Add user to organization
membership = OrganizationMembership.objects.create(
    user=user,
    organization=org,
    role='admin',  # 'viewer', 'operator', 'admin', 'owner'
    campus=campus,  # Optional: limit to specific campus
)
```

**Roles:**
- `viewer` - Read-only access
- `operator` - Can modify device assignments
- `admin` - Full access except billing
- `owner` - Full access including billing

## Service Layer Integration

All services accept optional tenant parameters:

```python
from micboard.services import DeviceService, LocationService

# Single-site mode (parameters ignored)
receivers = DeviceService.get_active_receivers()

# Multi-site mode
receivers = DeviceService.get_active_receivers(site_id=1)

# MSP mode
receivers = DeviceService.get_active_receivers(
    organization_id=org.id,
    campus_id=campus.id  # Optional
)

# Location filtering
locations = LocationService.get_all_locations(
    organization_id=org.id
)
```

### Backward Compatibility

All tenant parameters are optional and default to `None`. Existing code continues working without modification:

```python
# These all work identically
receivers = DeviceService.get_active_receivers()
receivers = DeviceService.get_active_receivers(organization_id=None)
receivers = DeviceService.get_active_receivers(site_id=None, campus_id=None)
```

## Managers & Querysets

### TenantAwareManager

The `TenantAwareManager` provides consistent filtering across deployment modes:

```python
from micboard.multitenancy.managers import TenantAwareManager

class MyModel(models.Model):
    # ... fields

    objects = TenantAwareManager()

# Usage
queryset = MyModel.objects.for_organization(organization=org)
queryset = MyModel.objects.for_campus(campus_id=campus.id)
queryset = MyModel.objects.for_site(site_id=1)
queryset = MyModel.objects.for_user(user=request.user)
```

Methods automatically handle single-site mode (no-op) vs multi-tenant mode (filtering).

## Middleware

### TenantMiddleware

Attaches organization context to requests:

```python
# In any view
def my_view(request):
    org = request.organization  # Current organization or None
    campus_id = request.campus_id  # Current campus ID or None

    # Use in service calls
    receivers = DeviceService.get_active_receivers(
        organization_id=org.id if org else None
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

## View Integration

Apply tenant filtering in your views by accessing the organization attached to the request:

```python
from django.http import JsonResponse
from django.views import View
from micboard.services import DeviceService

class ReceiverListAPIView(View):
    def get(self, request):
        # Get organization from request (attached by TenantMiddleware)
        org = getattr(request, 'organization', None)
        org_id = org.id if org else None

        # Filter receivers using the service layer
        receivers = DeviceService.get_active_receivers(
            organization_id=org_id
        )

        # Return as JSON
        return JsonResponse({
            "receivers": list(receivers.values())
        })
```

## Migration Guide

### From Single-Site to Multi-Site

1. Enable multi-site mode in settings
2. Run migrations
3. All buildings assigned to default site (SITE_ID=1)
4. No code changes needed

```bash
# settings.py: Set MICBOARD_MULTI_SITE_MODE = True
python manage.py migrate sites
python manage.py makemigrations micboard
python manage.py migrate micboard
```

### From Multi-Site to MSP

1. Enable MSP mode in settings
2. Run multitenancy migrations
3. Create default organization and campus
4. Assign buildings to organization/campus
5. Create user memberships

```bash
# settings.py: Set MICBOARD_MSP_ENABLED = True
python manage.py makemigrations micboard_multitenancy
python manage.py migrate micboard_multitenancy
python manage.py shell
```

```python
# In shell
from micboard.multitenancy.models import Organization, Campus
from micboard.models import Building

# Create default org/campus
org = Organization.objects.create(
    name='Default Organization',
    slug='default',
    site_id=1
)
campus = Campus.objects.create(
    organization=org,
    name='Main Campus',
    slug='main'
)

# Update buildings
Building.objects.all().update(
    organization=org,
    campus=campus
)
```

## Use Cases

### Large Enterprise (Single Org, Multi-Campus)

```python
# settings.py
MICBOARD_MSP_ENABLED = True
MICBOARD_SITE_ISOLATION = 'campus'
MICBOARD_ALLOW_ORG_SWITCHING = False  # Single org

# Users have campus-specific access
membership = OrganizationMembership.objects.create(
    user=av_tech,
    organization=university,
    campus=north_campus,  # Limited to North Campus only
    role='operator'
)
```

### MSP (Multiple Orgs)

```python
# settings.py
MICBOARD_MSP_ENABLED = True
MICBOARD_SITE_ISOLATION = 'organization'
MICBOARD_ALLOW_CROSS_ORG_VIEW = False  # Strict isolation
MICBOARD_SUBDOMAIN_ROUTING = True

# Each customer is separate org
church_a = Organization.objects.create(name='Church A', slug='church-a', site_id=1)
church_b = Organization.objects.create(name='Church B', slug='church-b', site_id=1)

# Users belong to their org only
OrganizationMembership.objects.create(user=tech1, organization=church_a, role='admin')
OrganizationMembership.objects.create(user=tech2, organization=church_b, role='admin')

# Subdomain routing: church-a.micboard.example.com → Church A
```

### Small Single-Site

```python
# settings.py
MICBOARD_MULTI_SITE_MODE = False
MICBOARD_MSP_ENABLED = False

# All features disabled, zero overhead
# Uses existing monitoring group filtering
```

## Testing

Test tenant isolation:

```python
from django.test import TestCase
from micboard.multitenancy.models import Organization, Campus
from micboard.services import DeviceService

class TenantIsolationTest(TestCase):
    def test_organization_isolation(self):
        org1 = Organization.objects.create(name='Org 1', slug='org1', site_id=1)
        org2 = Organization.objects.create(name='Org 2', slug='org2', site_id=1)

        # Create devices in each org
        # ... create buildings, locations, receivers

        # Verify isolation
        org1_receivers = DeviceService.get_active_receivers(organization_id=org1.id)
        org2_receivers = DeviceService.get_active_receivers(organization_id=org2.id)

        self.assertEqual(org1_receivers.count(), 5)
        self.assertEqual(org2_receivers.count(), 3)

        # Verify no cross-contamination
        self.assertNotIn(org2_receivers[0], org1_receivers)
```

## Performance Considerations

- **Indexes**: Added on `organization_id`, `campus_id`, `site_id` FKs
- **Query optimization**: Filters applied at database level
- **Single-site overhead**: Zero - features disabled via settings checks
- **Multi-site overhead**: Minimal - single JOIN added to queries
- **MSP overhead**: Moderate - additional JOINs for org/campus filtering

## Security

- **Tenant isolation**: Enforced at service layer and manager level
- **Superuser override**: Configurable via `MICBOARD_ALLOW_CROSS_ORG_VIEW`
- **Session hijacking**: Organization IDs validated against user memberships
- **Subdomain routing**: Requires proper DNS and SSL configuration

## Troubleshooting

### Buildings have no organization

```python
# Assign buildings to default org
from micboard.multitenancy.models import Organization
org = Organization.objects.first()
Building.objects.filter(organization__isnull=True).update(organization=org)
```

### User can't see devices

Check organization membership:

```python
from micboard.multitenancy.models import OrganizationMembership
memberships = OrganizationMembership.objects.filter(user=user, is_active=True)
print(f"User has {memberships.count()} active memberships")
```

### Queries returning empty

Verify feature flags:

```python
from django.conf import settings
print(f"Multi-site: {getattr(settings, 'MICBOARD_MULTI_SITE_MODE', False)}")
print(f"MSP: {getattr(settings, 'MICBOARD_MSP_ENABLED', False)}")
```

## API Reference

See `micboard.multitenancy` module for complete API documentation:

- `models.py` - Organization, Campus, OrganizationMembership
- `managers.py` - TenantAwareManager, TenantAwareQuerySet
- `middleware.py` - TenantMiddleware
- `admin.py` - Django admin interfaces
