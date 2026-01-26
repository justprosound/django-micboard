# Developer Quick Reference: Device Lifecycle Manager (Phase 3)

## Quick Start

### Import the Lifecycle Manager

```python
from micboard.services.device_lifecycle import get_lifecycle_manager, DeviceStatus

# Get manager for a manufacturer
lifecycle = get_lifecycle_manager('shure')  # or 'sennheiser'
```

### Common State Transitions

```python
# Mark device online
lifecycle.mark_online(receiver)

# Mark device offline with reason
lifecycle.mark_offline(receiver, reason="Device not responding")

# Mark device degraded with warnings
lifecycle.mark_degraded(receiver, warnings=["High temperature"])

# Mark device in maintenance
lifecycle.mark_maintenance(receiver, reason="Firmware update")

# Mark device retired (end-of-life)
lifecycle.mark_retired(receiver, reason="Replaced with new model")
```

### Query Device Status

```python
from micboard.models import Receiver
from micboard.services.device_lifecycle import DeviceStatus

# All active devices (online, degraded, provisioning)
active_devices = Receiver.objects.filter(
    status__in=DeviceStatus.active_states()
)

# Online devices only
online_devices = Receiver.objects.filter(status='online')

# Offline devices
offline_devices = Receiver.objects.filter(status='offline')

# Devices in maintenance
maintenance_devices = Receiver.objects.filter(status='maintenance')

# Using the computed property (use sparingly)
for receiver in Receiver.objects.all():
    if receiver.is_active:  # True if status in active_states()
        print(f"{receiver.name} is active")
```

### Device Status Values

```python
# Possible status values
'discovered'      # Found but not yet provisioned
'provisioning'    # Being configured
'online'          # Fully operational
'degraded'        # Operational but with warnings
'offline'         # Not responding
'maintenance'     # Intentionally offline
'retired'         # End of life
```

### In Polling Logic

```python
# During device polling/sync
def sync_from_api():
    lifecycle = get_lifecycle_manager('shure')

    for api_device in api_devices:
        receiver, created = Receiver.objects.update_or_create(
            api_device_id=api_device['id'],
            manufacturer=manufacturer,
            defaults={
                'ip': api_device['ip'],
                'name': api_device['name'],
            }
        )

        if created:
            # New device found
            lifecycle.mark_online(receiver)
        else:
            # Existing device - only transition if not stable
            if receiver.status not in {'online', 'degraded', 'maintenance'}:
                lifecycle.mark_online(receiver)
```

### In Admin Actions

```python
from django.contrib import admin
from micboard.services.device_lifecycle import get_lifecycle_manager

@admin.action(description='Force online')
def force_online(self, request, queryset):
    lifecycle = get_lifecycle_manager('shure')
    for receiver in queryset:
        lifecycle.mark_online(receiver)
    self.message_user(request, f"Marked {queryset.count()} devices online")

@admin.action(description='Mark offline')
def mark_offline(self, request, queryset):
    lifecycle = get_lifecycle_manager('shure')
    for receiver in queryset:
        lifecycle.mark_offline(receiver, reason="Admin action")
    self.message_user(request, f"Marked {queryset.count()} devices offline")
```

### Check Device Health

```python
# Auto-check and transition based on last_seen
lifecycle.check_device_health(receiver)

# This will:
# 1. Check if device hasn't been seen in 5 minutes
# 2. Auto-transition from online -> offline if timeout
# 3. Emit signals for UI updates
```

### Device Computed Properties

```python
receiver = Receiver.objects.get(pk=1)

# is_active property (computed from status)
print(receiver.is_active)  # True if status in active_states()

# Health status (computed from status + last_seen)
print(receiver.health_status)  # 'healthy', 'offline', 'stale', 'unknown'

# For transmitters
transmitter = receiver.transmitter
print(transmitter.is_active)  # True if status in active_states() AND last_seen < 5 min
```

## Migration from Old Pattern

### Before (Pre-Phase 3)
```python
# Direct field access (no longer works)
receiver.is_active = True
receiver.save(update_fields=['is_active'])

receiver.mark_online()  # Method no longer exists
receiver.mark_offline()  # Method no longer exists
```

### After (Phase 3)
```python
# Use lifecycle manager
lifecycle = get_lifecycle_manager('shure')
lifecycle.mark_online(receiver)    # Atomic, logged, broadcast
lifecycle.mark_offline(receiver)   # Atomic, logged, broadcast

# Check computed property (read-only)
if receiver.is_active:
    print("Device is active")
```

## Database Queries

### Efficient Queries

```python
# Use indexed fields directly
online = Receiver.objects.filter(status='online')  # Fast (indexed)
online_recent = Receiver.objects.filter(
    status__in=['online', 'degraded'],
    last_seen__gte=threshold
)  # Fast (indexed on status, last_seen)

# Avoid N+1 queries
receivers = Receiver.objects.select_related('manufacturer').all()
for receiver in receivers:
    print(receiver.is_active)  # No extra query, computed property
```

### Less Efficient Queries

```python
# Avoid full table scans
for receiver in Receiver.objects.all():
    if receiver.is_active:  # Works but slow for large datasets
        ...

# Instead use:
Receiver.objects.filter(status__in=['online', 'degraded', 'provisioning'])
```

## Test Setup

### Creating Test Fixtures

```python
from django.test import TestCase
from micboard.models import Receiver, Manufacturer

class MyTest(TestCase):
    def setUp(self):
        manufacturer = Manufacturer.objects.create(
            name="Shure", code="shure"
        )

        # Create receiver with online status
        self.receiver = Receiver.objects.create(
            name="Test Receiver",
            manufacturer=manufacturer,
            api_device_id="12345",
            status="online",  # Set status, not is_active
        )

        # Create offline receiver
        offline_receiver = Receiver.objects.create(
            name="Offline Receiver",
            manufacturer=manufacturer,
            api_device_id="67890",
            status="offline",  # Use status field
        )
```

### Updating Status in Tests

```python
# Update status
receiver.status = "offline"
receiver.save()

# Use lifecycle manager (recommended)
lifecycle = get_lifecycle_manager('shure')
lifecycle.mark_online(receiver)
```

## Signal Emissions

### Signals Emitted

```python
# When device status changes, these signals are emitted:
# 1. device_status_changed - sent with old/new values
# 2. sync_completed - sent after sync operations

# Listen to signals
from django.dispatch import receiver
from micboard.signals import device_status_changed

@receiver(device_status_changed)
def on_device_status_changed(sender, device, old_values, new_values, **kwargs):
    print(f"Device {device.name} changed from {old_values['status']} to {new_values['status']}")
```

## Performance Tips

### Use Manager Methods
```python
# Good: Uses lifecycle manager (atomic, logged, broadcast)
lifecycle.mark_online(receiver)

# Avoid: Direct field updates bypass lifecycle
receiver.status = 'online'
receiver.save()
```

### Batch Operations
```python
# Instead of looping
for receiver in receivers:
    lifecycle.mark_online(receiver)

# Consider using select_for_update for concurrent operations
receivers = Receiver.objects.select_for_update().filter(status='offline')
for receiver in receivers:
    lifecycle.mark_online(receiver)
```

### Query Optimization
```python
# Prefer indexed fields
Receiver.objects.filter(status='online')  # Fast
Receiver.objects.filter(status__in=['online', 'degraded'])  # Fast

# Avoid expensive filtering
for receiver in Receiver.objects.all():
    if receiver.is_active:  # Computes every record
        ...
```

## Troubleshooting

### Device Not Transitioning
```python
# Check current status
print(receiver.status)
print(receiver.is_active)
print(receiver.health_status)

# Manually transition
lifecycle = get_lifecycle_manager(receiver.manufacturer.code)
lifecycle.mark_online(receiver)
receiver.refresh_from_db()
```

### Queries Returning Wrong Results
```python
# Always use status field, not is_active property
# ❌ Wrong: Receiver.objects.filter(is_active=True)
# ✅ Right: Receiver.objects.filter(status__in=['online', 'degraded'])
```

### Tests Failing
```python
# Make sure test fixtures use status field
# ❌ Wrong: Receiver.objects.create(..., is_active=True)
# ✅ Right: Receiver.objects.create(..., status='online')

# And for updates
# ❌ Wrong: receiver.is_active = False; receiver.save()
# ✅ Right: receiver.status = 'offline'; receiver.save()
```

## Related Documentation

- [Device Lifecycle - Full Guide](DEVICE_LIFECYCLE_NO_BACKCOMPAT.md)
- [Services Quick Reference](docs/services-quick-reference.md)
- [Phase 3 Completion Summary](PHASE_3_COMPLETION_SUMMARY.md)
- [Copilot Instructions](.github/copilot-instructions.md)
