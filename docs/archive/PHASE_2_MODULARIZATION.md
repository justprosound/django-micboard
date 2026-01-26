# Django Micboard - Modularization & Best Practices Refactor

## Phase 2: Detailed Refactoring Plan (Post v25.01.15)

Based on current architecture and Django best practices, this plan addresses monolithic files, improves modularity, and enhances maintainability.

---

## 1. Models Refactoring - Split Monolithic Models

### Current Issue
Models likely contain too many responsibilities. Typical issues:
- Device models with mixed concerns (hardware state, assignment logic)
- Location models mixing physical and logical properties
- Manager logic duplicated across models

### Refactoring Strategy

#### 1.1 Split Device Model
```
Current: micboard/models/device.py (likely 200+ lines with mixed concerns)

Target:
- micboard/models/device.py      → Base Device abstract model
- micboard/models/receiver.py    → Receiver-specific model + ReceiverManager
- micboard/models/transmitter.py → Transmitter-specific model + TransmitterManager
- micboard/models/assignment.py  → New: Device-to-Location assignment
- micboard/models/state.py       → New: Separate device state tracking (battery, signal)
```

#### 1.2 Split Location Model
```
Current: micboard/models/location.py (likely 100+ lines)

Target:
- micboard/models/location.py    → Physical location only
- micboard/models/zone.py        → New: Logical grouping (different from physical location)
```

#### 1.3 Custom Managers - Extract to Separate File
```
New: micboard/models/managers.py
- class DeviceQuerySet
- class ReceiverManager
- class TransmitterManager
- class LocationManager
- Common filters: active, online, low_battery, weak_signal
```

### Implementation

**File**: `micboard/models/managers.py` (NEW)
```python
from django.db import models

class DeviceQuerySet(models.QuerySet):
    """Common device querysets."""
    def active(self):
        return self.filter(is_active=True)

    def online(self):
        return self.filter(is_online=True)

    def low_battery(self, threshold=20):
        return self.filter(battery_level__lt=threshold)

    def weak_signal(self, threshold=-80):
        return self.filter(signal_strength__lt=threshold)

class ReceiverManager(models.Manager):
    def get_queryset(self):
        return DeviceQuerySet(self.model).select_related('manufacturer', 'location')

class LocationManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().prefetch_related('receiver_set', 'transmitter_set')
```

---

## 2. Views Refactoring - Decouple View Logic

### Current Issue
Views likely contain:
- Business logic that should be in services
- Complex querysets and filtering
- Direct model manipulation
- Serialization mixed with view logic

### Refactoring Strategy

#### 2.1 Extract Business Logic to Services
```
Current: micboard/views/receivers.py (likely 150+ lines)

Target:
- micboard/views/receivers.py    → Thin API views (50 lines)
- micboard/services.py           → Business logic (ALREADY DONE - v25.01.15)
- micboard/api/viewsets.py       → DRF ViewSets using services
- micboard/api/permissions.py    → Custom permissions
- micboard/api/filters.py        → Custom filters
```

#### 2.2 Reorganize Views Structure
```
micboard/views/
├── __init__.py
├── receivers.py          → Receiver API ViewSet (uses ReceiverService)
├── transmitters.py       → Transmitter API ViewSet (uses TransmitterService)
├── locations.py          → Location API ViewSet (uses LocationService)
├── health.py             → Health check views (uses MonitoringService)
└── dashboard.py          → Dashboard/template views (read-only)

micboard/api/
├── __init__.py
├── routers.py            → API routing with SimpleRouter
├── pagination.py         → Custom pagination
├── filters.py            → DjangoFilterBackend configs
└── permissions.py        → Custom IsDeviceAdmin, IsLocationManager
```

#### 2.3 Move Complex Filtering to Filters
```
New: micboard/api/filters.py

from django_filters import FilterSet, CharFilter, BooleanFilter, RangeFilter

class ReceiverFilter(FilterSet):
    """Custom filters for Receiver API."""
    manufacturer = CharFilter(field_name='manufacturer__code')
    location = CharFilter(field_name='location__name')
    is_low_battery = BooleanFilter(method='filter_low_battery')

    def filter_low_battery(self, queryset, name, value):
        if value:
            return queryset.low_battery()
        return queryset

    class Meta:
        model = Receiver
        fields = ['is_online', 'manufacturer', 'location']
```

---

## 3. URL Routing - Organize with include()

### Current Issue
Likely all URLs in one monolithic `urls.py`. No app-specific routing organization.

### Refactoring Strategy

```
micboard/urls.py → Main app URLs
├── include('micboard.api.urls')       → API routes
├── include('micboard.websocket_urls')  → WebSocket handlers
└── include('micboard.dashboard.urls')  → Template views

micboard/api/urls.py (NEW)
from rest_framework.routers import SimpleRouter
from .viewsets import ReceiverViewSet, TransmitterViewSet, LocationViewSet

router = SimpleRouter()
router.register('receivers', ReceiverViewSet, basename='receiver')
router.register('transmitters', TransmitterViewSet, basename='transmitter')
router.register('locations', LocationViewSet, basename='location')

urlpatterns = router.urls  # Automatic CRUD routes

micboard/dashboard/urls.py (NEW)
urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('health/', HealthCheckView.as_view(), name='health'),
    path('admin/', AdminDashboardView.as_view(), name='admin_dashboard'),
]

micboard/websocket_urls.py (NEW)
websocket_urlpatterns = [
    re_path(r'ws/devices/$', DeviceConsumer.as_asgi()),
    re_path(r'ws/locations/(?P<location_id>\d+)/$', LocationConsumer.as_asgi()),
]
```

---

## 4. Utilities - Extract Reusable Code

### Current Issue
Common functionality scattered across files:
- Date/time utilities
- Permission checking logic
- Data validation
- Cache management
- API pagination

### Refactoring Strategy

```
micboard/utils/
├── __init__.py
├── validators.py        → Device ID validation, IP validation, etc.
├── cache.py             → Cache keys, TTL management
├── permissions.py       → Permission checking helpers
├── pagination.py        → Custom pagination classes
├── serialization.py     → Common serialization helpers
├── constants.py         → Magic numbers, enum-like constants
└── decorators.py        → Reusable decorators (ALREADY EXISTS - enhance it)

Example: micboard/utils/validators.py
def validate_device_id(device_id: str) -> bool:
    """Validate device ID format."""
    return bool(re.match(r'^[a-z]+_\d{4,}$', device_id))

def validate_ip_address(ip: str) -> bool:
    """Validate IPv4 address."""
    return bool(re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip))

Example: micboard/utils/cache.py
CACHE_KEYS = {
    'device': 'device:{manufacturer}:{device_id}',
    'location': 'location:{location_id}',
    'health': 'health:overall',
}

CACHE_TTL = {
    'device': 300,      # 5 minutes
    'location': 600,    # 10 minutes
    'health': 60,       # 1 minute
}
```

---

## 5. Serializers - Centralize and Organize

### Current Issue
Multiple serializers, possibly with code duplication.

### Refactoring Strategy

```
micboard/serializers/
├── __init__.py
├── base.py              → Common serializer logic
├── receivers.py         → Receiver serializers
├── transmitters.py      → Transmitter serializers
├── locations.py         → Location serializers
└── health.py            → Health check serializers

Example: micboard/serializers/__init__.py
from .receivers import ReceiverSerializer, ReceiverDetailSerializer
from .transmitters import TransmitterSerializer
from .locations import LocationSerializer

__all__ = [
    'ReceiverSerializer',
    'ReceiverDetailSerializer',
    'TransmitterSerializer',
    'LocationSerializer',
]

Example: micboard/serializers/base.py
from rest_framework import serializers

class BaseDeviceSerializer(serializers.ModelSerializer):
    """Base serializer with common device fields."""
    manufacturer_name = serializers.CharField(source='manufacturer.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)

    class Meta:
        fields = ['id', 'device_id', 'name', 'is_online', 'battery_level']
```

---

## 6. Tasks & Background Jobs - Organize Django-Q

### Current Issue
Background tasks likely scattered or embedded in views.

### Refactoring Strategy

```
micboard/tasks/
├── __init__.py
├── polling.py           → Polling orchestration
├── health_checks.py     → Health monitoring tasks
├── cleanup.py           → Maintenance tasks (delete old data, etc.)
└── webhooks.py          → Webhook notifications (future)

Example: micboard/tasks/polling.py
from django_q.tasks import schedule
from micboard.services import SynchronizationService

def poll_all_devices():
    """Poll all active manufacturers."""
    stats = {}
    for manufacturer in Manufacturer.objects.filter(is_active=True):
        stats[manufacturer.code] = SynchronizationService.sync_devices(
            manufacturer_code=manufacturer.code
        )
    return stats

def schedule_polling():
    """Schedule polling task."""
    schedule(
        'micboard.tasks.polling.poll_all_devices',
        repeat=300,  # Every 5 minutes
    )

Example: micboard/tasks/health_checks.py
def check_offline_devices():
    """Check for offline devices."""
    from micboard.services import SynchronizationService

    for manufacturer in Manufacturer.objects.filter(is_active=True):
        offline = SynchronizationService.detect_offline_devices(
            manufacturer_code=manufacturer.code,
            timeout_seconds=300,
        )
    return len(offline)
```

---

## 7. Signals - Move to Services (Already Done - v25.01.15)

### Current Status
✅ Already refactored in v25.01.15. Services layer replaces signals.

### Remaining Work
- Remove/deprecate any remaining signal handlers
- Document migration path for custom signal users

---

## 8. WebSocket/Real-Time Updates - Organize Channels

### Current Issue
Channels consumers likely mixed with other code.

### Refactoring Strategy

```
micboard/websockets/
├── __init__.py
├── consumers.py         → Channels consumers
├── routing.py           → WebSocket routing (ASGI patterns)
├── middleware.py        → Authentication middleware
└── serializers.py       → WebSocket-specific serialization

Example: micboard/websockets/consumers.py
from channels.generic.websocket import AsyncWebsocketConsumer
from micboard.services import MonitoringService
import json

class DeviceConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'devices'
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def device_update(self, event):
        """Handle device update message."""
        await self.send(text_data=json.dumps({
            'type': 'device_update',
            'device_id': event['device_id'],
            'battery_level': event['battery_level'],
        }))

Example: micboard/websockets/routing.py
from django.urls import path
from .consumers import DeviceConsumer, LocationConsumer

websocket_urlpatterns = [
    path('ws/devices/', DeviceConsumer.as_asgi()),
    path('ws/locations/<int:location_id>/', LocationConsumer.as_asgi()),
]
```

---

## 9. Permissions & Access Control - Centralize

### Current Issue
Permission logic scattered across views.

### Refactoring Strategy

```
micboard/permissions/
├── __init__.py
├── base.py              → Base permission classes
├── device.py            → Device-specific permissions
├── location.py          → Location-specific permissions
└── decorators.py        → Permission checking decorators

Example: micboard/permissions/device.py
from rest_framework.permissions import BasePermission

class IsDeviceAdmin(BasePermission):
    """Allow only device admins."""
    def has_permission(self, request, view):
        return request.user.groups.filter(name='device_admins').exists()

class CanViewDevice(BasePermission):
    """Allow if user can view this device's location."""
    def has_object_permission(self, request, view, obj):
        return obj.location in request.user.profile.accessible_locations.all()

Example: micboard/permissions/__init__.py
from .device import IsDeviceAdmin, CanViewDevice
from .base import IsAuthenticated, IsStaff

__all__ = ['IsDeviceAdmin', 'CanViewDevice', 'IsAuthenticated', 'IsStaff']
```

---

## 10. Testing - Organize by Module

### Current Status
✅ Test infrastructure in place (v25.01.15)

### Enhancement Strategy

```
tests/
├── conftest.py
├── test_models.py           ✅ Exists
├── test_services.py         ✅ Exists
├── test_integrations.py     ✅ Exists
├── test_e2e_workflows.py    ✅ Exists
├── unit/
│   ├── test_managers.py     📝 NEW: Manager tests
│   ├── test_validators.py   📝 NEW: Validator tests
│   └── test_utils.py        📝 NEW: Utility tests
├── api/
│   ├── test_viewsets.py     📝 NEW: ViewSet tests
│   ├── test_filters.py      📝 NEW: Filter tests
│   └── test_permissions.py  📝 NEW: Permission tests
└── websockets/
    ├── test_consumers.py    📝 NEW: Consumer tests
    └── test_messages.py     📝 NEW: Message tests
```

---

## Implementation Priority

### Week 1-2: Foundation
1. Create `micboard/models/managers.py` - Extract custom managers
2. Create `micboard/utils/` - Common utilities
3. Create `micboard/serializers/` - Organize serializers

### Week 3-4: Views & API
1. Create `micboard/api/` - REST API organization
2. Refactor `micboard/views/` - Move logic to services (already done)
3. Create `micboard/permissions/` - Permission classes

### Week 5-6: Real-time & Tasks
1. Organize `micboard/websockets/` - Channels consumers
2. Create `micboard/tasks/` - Background jobs
3. Update routing

### Week 7-8: Testing & Polish
1. Add module-specific tests
2. Update documentation
3. Performance optimization

---

## Refactoring Checklist

- [ ] Extract managers to `micboard/models/managers.py`
- [ ] Create `micboard/utils/` with validators, cache, constants
- [ ] Create `micboard/serializers/` package with organized modules
- [ ] Create `micboard/api/` with viewsets, filters, permissions
- [ ] Create `micboard/permissions/` with permission classes
- [ ] Organize `micboard/websockets/` for clarity
- [ ] Create `micboard/tasks/` for background jobs
- [ ] Add module-specific tests
- [ ] Update URL routing with `include()`
- [ ] Update documentation and inline comments
- [ ] Run full test suite (target: 95%+ coverage maintained)
- [ ] Update CHANGELOG.md with v25.02.DD release notes
- [ ] Deploy v25.02.DD release

---

## Expected Benefits

| Aspect | Before | After |
|--------|--------|-------|
| **File Size** | 200-400 lines | 50-100 lines |
| **Import Clarity** | Mixed concerns | Clear, focused imports |
| **Testability** | Medium | High (modular) |
| **Maintainability** | Difficult | Easy (clear structure) |
| **Reusability** | Low | High (services + utils) |
| **Documentation** | Scattered | Organized |
| **Onboarding Time** | High | Low |

---

## Notes

- All refactoring maintains backward compatibility at API level
- Services layer (v25.01.15) provides foundation for this phase
- Test coverage will be maintained at 95%+
- Each module gets focused unit tests
