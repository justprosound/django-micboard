# Device Lifecycle - No Backwards Compatibility Edition

**Status:** ✅ Refactored for Clean Architecture
**Key Change:** Removed all backwards compatibility - `is_active` is now a computed property

## What Changed

### Model Simplification

**Before:** Two fields (`is_active` + backwards-compatible methods)
```python
is_active = models.BooleanField(default=True)  # Field
def mark_online(self):
    self.is_active = True
    self.save(update_fields=['is_active'])
```

**After:** Single `status` field, `is_active` as computed property
```python
status = models.CharField(max_length=20, default='discovered')

@property
def is_active(self) -> bool:
    """Derived from status."""
    active_states = {'online', 'degraded', 'provisioning'}
    return self.status in active_states
```

### Benefits

- **Cleaner models:** Single source of truth (`status`)
- **Simpler queries:** No migration of dual fields
- **Better semantics:** `status` clearly represents lifecycle state
- **Easier testing:** No backwards-compat layer to mock
- **Type safety:** Status validated via enum/choices

### Breaking Changes

None - project was never released, so no external users affected.

### Migration

**Old Code Still Works:**
```python
receiver = Receiver.objects.get(pk=1)
if receiver.is_active:  # ✅ Works - computed property
    print(receiver.status)  # ✅ Works - now required
```

**No Model Method Updates Needed:**
```python
# Old pattern no longer needed:
receiver.mark_online()  # ❌ Removed

# New pattern instead:
from micboard.services.device_lifecycle import get_lifecycle_manager
lifecycle = get_lifecycle_manager(receiver.manufacturer.code)
lifecycle.mark_online(receiver)  # ✅ Direct, explicit
```

## Files Changed

- `micboard/models/receiver.py` - Removed `is_active` field, added computed property
- `micboard/models/transmitter.py` - Renamed `lifecycle_status` → `status`, added computed `is_active`
- `micboard/services/device_lifecycle.py` - Removed `is_active` assignments
- `micboard/admin/receivers.py` - Updated actions to use lifecycle manager
- `micboard/admin/channels.py` - Updated filter from `receiver__is_active` to `receiver__status`
- `micboard/migrations/0006_*.py` - Clean removal of `is_active` field

## Queries Now Use Status

### Before
```python
Receiver.objects.filter(is_active=True)  # Field query
```

### After
```python
# Explicit state check
Receiver.objects.filter(status__in=['online', 'degraded', 'provisioning'])

# Or use custom manager (future)
Receiver.objects.active()  # if we add manager method
```

## Example: Polling Loop

```python
from micboard.services.manufacturer_service import get_service
from micboard.services.device_lifecycle import get_lifecycle_manager

def poll_devices():
    service = get_service('shure')
    lifecycle = get_lifecycle_manager('shure')

    # Poll
    devices = service.poll_devices()

    for api_device in devices:
        receiver = Receiver.objects.get(api_device_id=api_device['id'])

        # Update from API
        service.update_device_from_api(receiver, api_device)

        # Check health (auto-transitions)
        lifecycle.check_device_health(receiver)

        # Query status (no more is_active field)
        if receiver.status == 'online':
            print(f'{receiver.name} is online')
```

## State Filtering

```python
from micboard.services.device_lifecycle import DeviceStatus

# All active devices
active = Receiver.objects.filter(status__in=DeviceStatus.active_states())

# All offline devices
offline = Receiver.objects.filter(status=DeviceStatus.OFFLINE.value)

# Specific transition
provisioning = Receiver.objects.filter(status='provisioning')

# Health status (computed from status + last_seen)
for receiver in active:
    print(f'{receiver.name}: {receiver.health_status}')
```

## Admin Interface

### List Filtering

Now filtered by `status` instead of `is_active`:
```python
list_filter = ('device_type', 'status', 'manufacturer')
```

### Admin Actions

Use lifecycle manager:
```python
@admin.action(description='Mark as online')
def mark_online(self, request, queryset):
    lifecycle = get_lifecycle_manager('shure')
    for receiver in queryset:
        lifecycle.mark_online(receiver)
```

## Migration Path

✅ **Already Applied:** `0006_remove_receiver_micboard_re_is_acti_7d55e8_idx_and_more.py`

**What It Does:**
1. Removes `is_active` BooleanField from Receiver
2. Adds `status` CharField to Receiver (already existed from 0005)
3. Adds `updated_at` DateTimeField to Receiver
4. Renames `lifecycle_status` → `status` on Transmitter
5. Replaces index on `is_active` with index on `status, last_seen`

**To Apply:**
```bash
python manage.py migrate micboard
```

## Database Query Performance

### Index on Status + Last Seen

```python
# Efficient (indexed)
Receiver.objects.filter(status='online', last_seen__gte=threshold)

# Efficient (indexed)
Receiver.objects.filter(status='offline')

# Less efficient (full table scan for computed property)
for r in receivers:
    if r.is_active:  # Computed property, no query
        ...
```

## Code Examples

### Check Device Status

```python
receiver = Receiver.objects.get(ip='192.168.1.1')

print(receiver.status)  # 'online', 'offline', etc.
print(receiver.is_active)  # True/False (computed)
print(receiver.health_status)  # 'healthy', 'offline', 'stale', etc.
```

### Update Device Status

```python
from micboard.services.device_lifecycle import get_lifecycle_manager

lifecycle = get_lifecycle_manager('shure')

# State transition
lifecycle.mark_online(receiver)
lifecycle.mark_offline(receiver, reason='Timeout')
lifecycle.mark_degraded(receiver, warnings=['High temp'])
lifecycle.mark_maintenance(receiver, reason='Firmware update')

# Status is now updated atomically and logged
assert receiver.status == 'online'
assert receiver.is_active is True
```

### Admin Action Example

```python
@admin.action(description='Enable for maintenance')
def maintenance_mode(modeladmin, request, queryset):
    lifecycle = get_lifecycle_manager('shure')

    for receiver in queryset:
        lifecycle.mark_maintenance(
            receiver,
            reason=f'Admin action by {request.user.username}'
        )

    modeladmin.message_user(
        request,
        f'{queryset.count()} devices in maintenance mode'
    )
```

## Testing

```python
import pytest
from micboard.models import Receiver
from micboard.services.device_lifecycle import DeviceStatus, get_lifecycle_manager

@pytest.mark.django_db
def test_status_property():
    receiver = Receiver.objects.create(
        status=DeviceStatus.ONLINE.value,
        ...
    )

    # is_active derived from status
    assert receiver.is_active is True

    receiver.status = DeviceStatus.OFFLINE.value
    assert receiver.is_active is False

    receiver.status = DeviceStatus.MAINTENANCE.value
    assert receiver.is_active is False

@pytest.mark.django_db
def test_health_status():
    from django.utils import timezone
    from datetime import timedelta

    receiver = Receiver.objects.create(
        status=DeviceStatus.ONLINE.value,
        last_seen=timezone.now() - timedelta(minutes=1),
        ...
    )

    assert receiver.health_status == 'healthy'

    receiver.last_seen = timezone.now() - timedelta(hours=1)
    assert receiver.health_status == 'stale'
```

## Summary

- ✅ **No backwards compatibility needed** - Single source of truth (`status`)
- ✅ **Cleaner code** - `is_active` is computed property
- ✅ **Simpler models** - No dual fields or wrapper methods
- ✅ **Atomic transitions** - All state changes via lifecycle manager
- ✅ **Migration applied** - Database schema updated
- ✅ **Ready to use** - System check passes

**Next Steps:** Refactor Shure integration to use lifecycle manager for all state updates.
