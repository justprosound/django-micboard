# Device Lifecycle - Quick Start

**Status:** ✅ Implemented and Migrated

## What Changed

**Before:** Signal-driven state management - hard to debug and test  
**After:** Direct lifecycle management - testable, atomic, validated

## Key Concepts

### 1. Seven Lifecycle States

```
DISCOVERED → PROVISIONING → ONLINE ⇄ DEGRADED → MAINTENANCE
                              ↓         ↓            ↓
                          OFFLINE ─────────────→ RETIRED
```

### 2. DeviceLifecycleManager

Central service for ALL device state changes:

```python
from micboard.services.device_lifecycle import get_lifecycle_manager

lifecycle = get_lifecycle_manager(service_code='shure')

# Mark device online with health data
lifecycle.mark_online(receiver, health_data={'uptime': 3600})

# Mark degraded with warnings
lifecycle.mark_degraded(receiver, warnings=['High temperature', 'Low battery'])

# Mark offline with reason
lifecycle.mark_offline(receiver, reason='Connection timeout after 30s')

# Maintenance mode (pushes to API)
lifecycle.mark_maintenance(receiver, reason='Firmware update')

# Auto health check (transitions based on last_seen)
status = lifecycle.check_device_health(receiver, threshold_minutes=5)
```

### 3. Bi-Directional Sync

**Pull from API:**
```python
service = get_service('shure')
api_data = {'name': 'New Name', 'state': 'ONLINE', 'firmware_version': '1.2.3'}

# Updates model AND transitions state
service.update_device_from_api(receiver, api_data)
```

**Push to API:**
```python
# Update local model
receiver.name = 'Stage Left'
receiver.save()

# Sync to manufacturer API
service.sync_device_to_api(receiver, fields=['name'])
```

### 4. Minimal Signals

Signals only for decoupled concerns:

```python
# ✅ Kept: WebSocket broadcasts
device_status_changed.send(...)  # UI updates
sync_completed.send(...)          # UI notifications

# ❌ Removed: Business logic signals
device_discovered  # Logic moved to DeviceLifecycleManager
device_online      # Logic moved to DeviceLifecycleManager
device_offline     # Logic moved to DeviceLifecycleManager
device_updated     # Logic moved to DeviceLifecycleManager
```

## Usage Examples

### In Manufacturer Service

```python
class ShureService(ManufacturerService):
    def poll_devices(self):
        devices = self.get_client().list_devices()
        
        for api_device in devices:
            receiver = Receiver.objects.get(api_device_id=api_device['id'])
            
            # Pull sync (updates fields AND state)
            self.update_device_from_api(receiver, api_device)
            
            # Auto health check
            self.check_device_health(receiver, threshold_minutes=5)
        
        # Notify UI
        self.emit_sync_complete({'device_count': len(devices)})
```

### In Admin Actions

```python
@admin.action(description='Put in maintenance mode')
def maintenance_mode(modeladmin, request, queryset):
    lifecycle = get_lifecycle_manager('shure')
    
    for receiver in queryset:
        lifecycle.mark_maintenance(
            receiver,
            reason=f'Admin action by {request.user.username}'
        )
```

### In Management Commands

```python
def handle(self, *args, **options):
    service = get_service('shure')
    receivers = Receiver.objects.all()
    
    # Bulk health check
    results = service.bulk_health_check(receivers, threshold_minutes=5)
    # Returns: {'online': 45, 'offline': 3, 'degraded': 2, ...}
```

## Model Changes

Both `Receiver` and `Transmitter` now have:

```python
# NEW
status = CharField(max_length=20, default='discovered')
updated_at = DateTimeField(auto_now=True)

# Transmitter also has
lifecycle_status = CharField(max_length=20, default='discovered')
last_seen = DateTimeField(null=True, blank=True)

# Backwards-compatible methods
def mark_online(self):
    self.status = 'online'
    self.is_active = True
    self.last_seen = timezone.now()
    self.save(update_fields=['status', 'is_active', 'last_seen', 'updated_at'])
```

## Migration Applied

```bash
python manage.py migrate micboard
# ✅ Applied: 0006_receiver_status_receiver_updated_at_and_more.py
```

## Files Reference

- `micboard/services/device_lifecycle.py` - Core lifecycle logic
- `micboard/services/manufacturer_service.py` - Service integration
- `micboard/services/shure_service_example.py` - Complete example
- `micboard/signals/handlers.py` - Minimal broadcasts only
- `docs/DEVICE_LIFECYCLE_REFACTORING.md` - Full documentation

## Testing

```python
from micboard.services.device_lifecycle import DeviceLifecycleManager, DeviceStatus

def test_lifecycle():
    manager = DeviceLifecycleManager('shure')
    receiver.status = DeviceStatus.DISCOVERED.value
    
    # Valid transitions work
    assert manager.transition_device(receiver, DeviceStatus.PROVISIONING.value)
    assert manager.transition_device(receiver, DeviceStatus.ONLINE.value)
    
    # Invalid transitions blocked
    receiver.status = DeviceStatus.RETIRED.value
    assert not manager.transition_device(receiver, DeviceStatus.ONLINE.value)
```

## Next Steps

1. **Refactor existing Shure integration** to use lifecycle methods
2. **Update poll_devices command** to use `service.update_device_from_api()`
3. **Add admin actions** for manual state transitions
4. **Test WebSocket broadcasts** for real-time UI updates
5. **Implement push sync** for configuration changes

## Benefits

✅ **Testable** - Direct method calls, no signal spaghetti  
✅ **Debuggable** - Clear stack traces, single source of truth  
✅ **Atomic** - Transactions with row locking  
✅ **Validated** - State machine enforces valid transitions  
✅ **Audited** - Automatic logging via StructuredLogger  
✅ **Bi-directional** - Pull from API, push to API  
✅ **Minimal Signals** - Only for WebSocket/UI, not business logic
