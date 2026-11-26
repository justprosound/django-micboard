---
title: "Enable multi-tenancy"
description: "Turn on multi-site or MSP mode, create organizations and memberships, and troubleshoot visibility."
type: how-to
audience: developer
---
How tenancy works is explained in [Multi-tenancy and MSP support](multitenancy.md).

## Choose a mode

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
uv run --no-sync python manage.py migrate
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
uv run --no-sync python manage.py migrate
```

## Tune the mode

### Settings

Configure the required values explicitly in the host settings module:

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


## Create an organization, campus and membership

```python
from micboard.multitenancy.models import Campus, Organization, OrganizationMembership

org = Organization.objects.create(name="University A", slug="university-a", site_id=1)
campus = Campus.objects.create(organization=org, name="North Campus", slug="north")

# role is one of 'viewer', 'operator', 'admin', 'owner'; campus is optional
OrganizationMembership.objects.create(user=user, organization=org, campus=campus, role="operator")
```

## Scope a view to the current user

Apply tenant filtering in your views by accessing the organization attached to the request:

```python
from micboard.services.shared.visibility import visible_to
from django.http import JsonResponse
from django.views import View
from micboard.models.hardware.wireless_chassis import WirelessChassis

class ReceiverListAPIView(View):
    def get(self, request):
        chassis = visible_to(WirelessChassis, user=request.user).filter(
    status__in=("online", "degraded", "provisioning"),
)

        # Return as JSON
        return JsonResponse({
            "chassis": list(chassis.values())
        })
```


## Move between modes

### From Single-Site to Multi-Site

1. Enable multi-site mode in settings
2. Run migrations
3. All buildings assigned to default site (SITE_ID=1)
4. No code changes needed

```bash
# settings.py: Set MICBOARD_MULTI_SITE_MODE = True
uv run --no-sync python manage.py migrate
```

### From Multi-Site to MSP

1. Enable MSP mode in settings
2. Run multitenancy migrations
3. Create default organization and campus
4. Assign buildings to organization/campus
5. Create user memberships

```bash
# settings.py: Set MICBOARD_MSP_ENABLED = True
uv run --no-sync python manage.py migrate
uv run --no-sync python manage.py shell
```

```python
# In shell
from micboard.multitenancy.models import Organization, Campus
from micboard.models.locations.structure import Building

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
    organization_id=org.pk,
    campus_id=campus.pk,
)
```


## Examples

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


## Test tenant isolation

Test tenant isolation:

```python
from micboard.services.shared.visibility import visible_to
from django.test import TestCase
from micboard.multitenancy.models import Organization, Campus
from micboard.models.hardware.wireless_chassis import WirelessChassis

class TenantIsolationTest(TestCase):
    def test_organization_isolation(self):
        org1 = Organization.objects.create(name='Org 1', slug='org1', site_id=1)
        org2 = Organization.objects.create(name='Org 2', slug='org2', site_id=1)

        # Create devices in each org
        # ... create buildings, locations, receivers

        # Verify isolation through users with memberships in each organization
        org1_chassis = visible_to(WirelessChassis, user=org1_user)
        org2_chassis = visible_to(WirelessChassis, user=org2_user)

        self.assertEqual(org1_chassis.count(), 5)
        self.assertEqual(org2_chassis.count(), 3)

        # Verify no cross-contamination
        self.assertNotIn(org2_chassis[0], org1_chassis)
```


## Troubleshooting

### Buildings have no organization

```python
# Assign buildings to default org
from micboard.multitenancy.models import Organization
org = Organization.objects.first()
Building.objects.filter(organization_id__isnull=True).update(organization_id=org.pk)
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
from micboard.services.settings.settings_service import settings as micboard_settings

print(f"Multi-site: {micboard_settings.multi_site_mode}")
print(f"MSP: {micboard_settings.msp_enabled}")
```

