# Multi-Tenancy Quick Reference

## 🚀 Quick Start

### Option 1: Single-Site (Default) - No Changes Needed
```python
# settings.py - Already configured
MICBOARD_MULTI_SITE_MODE = False
MICBOARD_MSP_ENABLED = False
```

### Option 2: Multi-Site Mode
```python
# settings.py
INSTALLED_APPS = ['django.contrib.sites', 'micboard', ...]
SITE_ID = 1
MICBOARD_MULTI_SITE_MODE = True
```

```bash
uv run --no-sync python manage.py migrate
```

### Option 3: MSP Mode (Full Multi-Tenancy)
```python
# settings.py
INSTALLED_APPS = [
    'django.contrib.sites',
    'micboard',
    'micboard.multitenancy',  # Add this
    ...
]
SITE_ID = 1
MICBOARD_MULTI_SITE_MODE = True
MICBOARD_MSP_ENABLED = True
MIDDLEWARE += ['micboard.multitenancy.middleware.TenantMiddleware']
```

```bash
uv run --no-sync python manage.py migrate
```

## 📦 Service Layer Usage

### HardwareQueryService

```python
from micboard.services.core.hardware_query import HardwareQueryService

# Single-site (default)
chassis = HardwareQueryService.get_active_chassis()

# Multi-site
chassis = HardwareQueryService.get_active_chassis(site_id=1)

# MSP mode
chassis = HardwareQueryService.get_active_chassis(
    organization_id=org.id,
    campus_id=campus.id  # Optional
)
```

### LocationService

```python
from micboard.services.core.location import LocationService

# Get all locations (tenant-aware)
locations = LocationService.get_all_locations(
    organization_id=org.id,
    campus_id=campus.id
)
```

### ManufacturerSyncService

```python
from micboard.services.manufacturer.sync import ManufacturerSyncService

# Sync devices for organization
result = ManufacturerSyncService.sync_devices_for_manufacturer(
    manufacturer_code='shure',
    organization_id=org.id,
    campus_id=campus.id
)
```

## 🏢 Creating Organizations

```python
from micboard.multitenancy.models import Organization, Campus

# Create organization
org = Organization.objects.create(
    name='University A',
    slug='university-a',
    site_id=1,
    subscription_tier='enterprise',
    max_devices=500
)

# Create campus
campus = Campus.objects.create(
    organization=org,
    name='North Campus',
    slug='north',
    city='Boston',
    state='MA'
)

# Assign buildings
from micboard.models.locations.structure import Building
Building.objects.filter(name__contains='Engineering').update(
    organization_id=org.pk,
    campus_id=campus.pk,
)
```

## 👥 User Access

```python
from micboard.multitenancy.models import OrganizationMembership
from django.contrib.auth.models import User

user = User.objects.get(username='av_tech')

# Add user to organization
membership = OrganizationMembership.objects.create(
    user=user,
    organization=org,
    campus=campus,  # Optional: limit to campus
    role='operator'  # viewer/operator/admin/owner
)
```

## 🔍 Tenant-Aware Managers

```python
from micboard.models.base_managers import TenantOptimizedManager

class MyModel(models.Model):
    objects = TenantOptimizedManager()

# Usage
qs = MyModel.objects.for_organization(organization=org)
qs = MyModel.objects.for_campus(campus_id=campus.id)
qs = MyModel.objects.for_user(user=request.user)
```

## 🌐 Request Context (Views)

```python
def my_view(request):
    # Access current organization
    org = request.organization  # Set by TenantMiddleware
    campus_id = request.campus_id

    # Use in service calls
    chassis = HardwareQueryService.get_active_chassis(
        organization_id=org.id if org else None
    )
```

## 🔄 Organization Switching

```python
# Allow users to switch between organizations
def switch_org(request, org_id):
    # Verify user has access
    if OrganizationMembership.objects.filter(
        user=request.user,
        organization_id=org_id,
        is_active=True
    ).exists():
        request.session['current_organization_id'] = org_id
    return redirect('dashboard')
```

## 🎨 Subdomain Routing (Optional)

```python
# settings.py
MICBOARD_SUBDOMAIN_ROUTING = True
MICBOARD_ROOT_DOMAIN = 'micboard.example.com'

# Access via subdomain
# university-a.micboard.example.com → Organization(slug='university-a')
# church-b.micboard.example.com → Organization(slug='church-b')
```

## 📊 Roles & Permissions

| Role | Permissions |
|------|-------------|
| `viewer` | Read-only access |
| `operator` | Can modify device assignments |
| `admin` | Full access except billing |
| `owner` | Full access including billing |

```python
# Check permissions
if membership.can_modify_devices():
    # Allow device changes
    pass

if membership.can_manage_users():
    # Allow user management
    pass
```

## 🗂️ Files Created

```
micboard/
├── multitenancy/
│   ├── __init__.py          # Conditional imports
│   ├── models.py            # Organization/Campus/Membership
│   ├── middleware.py        # TenantMiddleware
│   ├── admin.py             # Django admin
│   └── apps.py              # App config
├── settings/
│   └── multitenancy.py      # Settings template
└── models/
    ├── base_managers.py     # Canonical tenant-aware manager
    └── locations/           # Indexed tenant identifiers

docs/
└── multitenancy.md          # Full documentation
```

## 📚 Documentation Links

- **Full Documentation**: [multitenancy.md](multitenancy.md)
- **Migration Guide**: [micboard/multitenancy/migrations/README.md](https://github.com/justprosound/django-micboard/blob/main/micboard/multitenancy/migrations/README.md)
- **Settings Template**: [micboard/settings/multitenancy.py](https://github.com/justprosound/django-micboard/blob/main/micboard/settings/multitenancy.py)

## ✅ Backward Compatibility

All tenant parameters are **optional** - existing code works unchanged:

```python
# ✅ All of these work
HardwareQueryService.get_active_chassis()
HardwareQueryService.get_active_chassis(organization_id=1)
HardwareQueryService.get_active_chassis(site_id=1, campus_id=2)
```

## 🧪 Testing

```python
from micboard.multitenancy.models import Organization
from micboard.models.hardware.wireless_chassis import WirelessChassis

# Create test organization
org = Organization.objects.create(name='Test Org', slug='test', site_id=1)

# Test isolation
receivers = WirelessChassis.objects.for_organization(organization=org)
assert all(r.location.building.organization_id == org.pk for r in receivers)
```

## 🚨 Common Issues

### "Building has no organization"
```python
# Assign buildings to default org
org = Organization.objects.first()
Building.objects.filter(organization_id__isnull=True).update(organization_id=org.pk)
```

### "User can't see devices"
```python
# Check memberships
from micboard.multitenancy.models import OrganizationMembership
OrganizationMembership.objects.filter(user=user, is_active=True)
```

### "Settings not configured"
```python
# Ensure Django settings loaded before importing multitenancy
import django
django.setup()
from micboard.multitenancy import is_msp_enabled
```

## 🎯 Use Case Examples

### Small Church (Single-Site)
```python
# No configuration needed - runs with zero overhead
MICBOARD_MSP_ENABLED = False
```

### University (Multi-Campus)
```python
MICBOARD_MSP_ENABLED = True
MICBOARD_SITE_ISOLATION = 'campus'

# Campus-specific users
OrganizationMembership.objects.create(
    user=av_tech,
    organization=university,
    campus=north_campus,
    role='operator'
)
```

### MSP Provider
```python
MICBOARD_MSP_ENABLED = True
MICBOARD_SITE_ISOLATION = 'organization'
MICBOARD_ALLOW_CROSS_ORG_VIEW = False
MICBOARD_SUBDOMAIN_ROUTING = True

# Each customer is separate organization
church_a = Organization.objects.create(name='Church A', ...)
church_b = Organization.objects.create(name='Church B', ...)
```
