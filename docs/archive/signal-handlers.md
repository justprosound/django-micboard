# Signal Handlers Implementation

## Overview

The Phase 4 signal handlers provide comprehensive event-driven logging for device lifecycle events. They integrate with the `ManufacturerService` signals and automatically log all device activity to `ActivityLog`.

## Signals and Handlers

### 1. **device_discovered** → `handle_device_discovered()`

**Purpose:** Logs when new devices are discovered during network scans.

**Signal Parameters:**
- `service_code`: Manufacturer service code (e.g., "shure")
- `device_data`: Dict with device details (id, name, type, model, ip_address)

**Handler Actions:**
- Creates `ActivityLog` entry with type "discovery"
- Logs to console with device details
- Future: Could auto-provision devices to database

**Example:**
```python
from micboard.services.manufacturer_service import device_discovered

device_discovered.send(
    sender=ShureService,
    service_code="shure",
    device_data={
        "id": "ULXD4D-001",
        "name": "Receiver 1",
        "type": "receiver",
        "model": "ULXD4D",
        "ip_address": "172.21.10.100",
    },
)
```

### 2. **device_online** → `handle_device_online()`

**Purpose:** Updates device status and logs when devices come online.

**Signal Parameters:**
- `service_code`: Manufacturer service code
- `device_id`: Device API identifier (matches `api_device_id`)
- `device_type`: Type (receiver/transmitter)

**Handler Actions:**
- Looks up device by `manufacturer__code` + `api_device_id`
- Calls `device.mark_online()` (sets `is_active=True`, updates `last_seen`)
- Logs CRUD update with old/new status
- Creates service ActivityLog
- Logs warning if device not found in database

**Example:**
```python
device_online.send(
    sender=ShureService,
    service_code="shure",
    device_id="ULXD4D-001",
    device_type="receiver",
)
```

### 3. **device_offline** → `handle_device_offline()`

**Purpose:** Updates device status and logs when devices go offline.

**Signal Parameters:**
- `service_code`: Manufacturer service code
- `device_id`: Device API identifier
- `device_type`: Type (receiver/transmitter)

**Handler Actions:**
- Looks up device by `manufacturer__code` + `api_device_id`
- Calls `device.mark_offline()` (sets `is_active=False`)
- Logs CRUD update with old/new status
- Creates service ActivityLog with "warning" status
- Logs warning if device not found

**Example:**
```python
device_offline.send(
    sender=ShureService,
    service_code="shure",
    device_id="ULXD4D-001",
    device_type="receiver",
)
```

### 4. **device_updated** → `handle_device_updated()`

**Purpose:** Logs when device data changes during polling.

**Signal Parameters:**
- `service_code`: Manufacturer service code
- `device_id`: Device API identifier
- `device_type`: Type (receiver/transmitter)
- `old_data`: Previous device data dict
- `new_data`: Updated device data dict

**Handler Actions:**
- Compares old_data and new_data to find changed fields
- Creates ActivityLog with changed field details
- Logs field names and old/new values
- Future: Broadcast via WebSocket for real-time dashboard updates

**Example:**
```python
device_updated.send(
    sender=ShureService,
    service_code="shure",
    device_id="ULXD4D-001",
    device_type="receiver",
    old_data={"ip_address": "172.21.10.100", "firmware": "1.0.0"},
    new_data={"ip_address": "172.21.10.101", "firmware": "1.0.1"},
)
```

### 5. **device_synced** → `handle_device_synced()`

**Purpose:** Logs completion of device synchronization operations.

**Signal Parameters:**
- `service_code`: Manufacturer service code
- `sync_result`: Dict with sync stats and status

**Sync Result Fields:**
- `device_count`: Total devices discovered
- `online_count`: Devices currently online
- `error_count`: Sync errors encountered
- `status`: "success" or "error"
- `duration_seconds`: Sync duration
- `error_message`: Error details if failed

**Handler Actions:**
- Creates ActivityLog entry with type "sync"
- Logs sync statistics to console
- Future: Update `ServiceSyncLog` completion data

**Example:**
```python
device_synced.send(
    sender=ShureService,
    service_code="shure",
    sync_result={
        "device_count": 15,
        "online_count": 12,
        "error_count": 0,
        "status": "success",
        "duration_seconds": 2.5,
    },
)
```

## Integration

### Automatic Registration

Handlers are automatically connected to signals when Django starts:

**`micboard/signals/__init__.py`:**
```python
# Import handlers to register them
from . import handlers  # noqa: F401
```

**`micboard/apps.py` (MicboardConfig.ready()):**
```python
def ready(self):
    # Import signals to register them
    from . import signals  # noqa: F401
```

### Manual Signal Connection

If needed, handlers can be manually connected:

```python
from micboard.services.manufacturer_service import device_discovered
from micboard.signals.handlers import handle_device_discovered

device_discovered.connect(handle_device_discovered)
```

## Device Lookup Logic

Handlers lookup devices using the compound key:
```python
device = Receiver.objects.get(
    manufacturer__code=service_code,  # e.g., "shure"
    api_device_id=device_id,          # e.g., "ULXD4D-001"
)
```

**Important:** The `device_id` parameter must match the `api_device_id` field in the database, NOT the `name` field.

## Testing

Run comprehensive signal handler tests:

```bash
python scripts/test_signal_handlers.py
```

**Test Coverage:**
- ✅ device_discovered creates ActivityLog
- ✅ device_online updates is_active to True
- ✅ device_offline updates is_active to False
- ✅ device_updated logs changed fields
- ✅ device_synced logs sync completion

**Example Test Output:**
```
============================================================
Testing Device Lifecycle Signal Handlers
============================================================

=== Testing device_discovered signal ===
✓ ActivityLog created: Discovered receiver device: Test Receiver

=== Testing device_online signal ===
✓ Receiver status updated: is_active=True
✓ ActivityLog created: shure - Device online: test-receiver-001 (receiver)

...

============================================================
✓ ALL TESTS PASSED
============================================================
```

## ActivityLog Entries

All handlers create `ActivityLog` entries that appear in:

1. **Django Admin** → Activity Logs
   - Filter by activity_type, operation, status
   - Search by summary
   - View detailed JSON data

2. **Admin Dashboard** → Recent Activities
   - Real-time activity feed
   - Last 50 activities displayed
   - Auto-refreshes via AJAX

3. **REST API** → `/api/v2/activity-logs/`
   - Paginated list (50/page)
   - Filter by type, status, date range

## Console Logging

Handlers log to `micboard.signals.handlers` logger:

```python
INFO 2026-01-22 12:29:25,674 micboard.signals.handlers Device discovered: Test Receiver (receiver) from shure
INFO 2026-01-22 12:29:25,776 micboard.signals.handlers Device came online: test-receiver-001 (receiver)
INFO 2026-01-22 12:29:25,899 micboard.signals.handlers Device went offline: test-receiver-001 (receiver)
```

Configure in `settings.py`:
```python
LOGGING = {
    "loggers": {
        "micboard.signals": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}
```

## Future Enhancements

### 1. WebSocket Broadcasting

Add real-time dashboard updates:

```python
@receiver(device_online)
def handle_device_online(...):
    # ... existing logic ...

    # Broadcast to WebSocket clients
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "dashboard",
        {
            "type": "device.online",
            "device_id": device_id,
            "device_type": device_type,
        },
    )
```

### 2. Auto-Provisioning

Automatically create devices on discovery:

```python
@receiver(device_discovered)
def handle_device_discovered(...):
    # ... existing logic ...

    if settings.MICBOARD_CONFIG.get("AUTO_PROVISION_DEVICES"):
        manufacturer = Manufacturer.objects.get(code=service_code)

        if device_data["type"] == "receiver":
            Receiver.objects.get_or_create(
                manufacturer=manufacturer,
                api_device_id=device_data["id"],
                defaults={
                    "name": device_data["name"],
                    "device_type": device_data["model"],
                    "ip": device_data["ip_address"],
                },
            )
```

### 3. Alert System

Send alerts for critical events:

```python
@receiver(device_offline)
def handle_device_offline(...):
    # ... existing logic ...

    # Check if device is critical
    if device and device.location and device.location.alert_on_offline:
        from micboard.tasks.alerts import send_device_offline_alert
        send_device_offline_alert.async_task(device.pk)
```

### 4. ServiceSyncLog Tracking

Track sync operations from start to finish:

```python
# In ShureService.poll_devices():
sync_log = ServiceSyncLog.objects.create(
    service=self.code,
    started_at=timezone.now(),
    status="running",
)

try:
    # ... poll devices ...

    device_synced.send(
        sender=self,
        service_code=self.code,
        sync_result={...},
        sync_log_id=sync_log.pk,  # Pass ID
    )
finally:
    sync_log.completed_at = timezone.now()
    sync_log.status = "success" if no errors else "error"
    sync_log.save()
```

## Best Practices

1. **Always emit signals** from manufacturer services
2. **Use api_device_id** for device lookups, not name
3. **Include context** in signal data (service_code, timestamps)
4. **Handle missing devices** gracefully (log warnings)
5. **Test signal handlers** after making changes
6. **Monitor ActivityLog** for unexpected patterns

## Related Documentation

- [Services Architecture](services-architecture.md) - ManufacturerService base class
- [Activity Logging](activity-logging.md) - ActivityLog model and methods
- [Admin Dashboard](admin-dashboard.md) - Viewing signal-generated logs
- [REST API](../api/endpoints.md) - API access to activity logs
