# Device Lifecycle - Visual Architecture

## State Transition Diagram

```
┌─────────────┐
│  DISCOVERED │  ← Device found via API discovery
└──────┬──────┘
       │
       ├─→ configure/provision
       │
       ↓
┌─────────────┐
│ PROVISIONING│  ← Being configured (DHCP, name, channels)
└──────┬──────┘
       │
       ├─→ setup complete
       │
       ↓
┌─────────────┐     ┌───────────┐
│   ONLINE    │←───→│ DEGRADED  │  ← Has warnings (temp, battery, signal)
└──────┬──────┘     └─────┬─────┘
       │                  │
       │                  │
       ├─→ connection lost, timeout
       │                  │
       ↓                  ↓
┌─────────────┐
│   OFFLINE   │  ← Not responding to polls
└──────┬──────┘
       │
       ├─→ admin action
       │
       ↓
┌─────────────┐
│ MAINTENANCE │  ← Administratively disabled (firmware update, repair)
└──────┬──────┘
       │
       ├─→ decommission
       │
       ↓
┌─────────────┐
│   RETIRED   │  ← End of life (terminal state, no transitions out)
└─────────────┘
```

## Data Flow Architecture

### Pull Sync (API → Database)

```
┌──────────────────┐
│ Manufacturer API │  (Shure System API)
└────────┬─────────┘
         │
         │ HTTP GET /devices
         │
         ↓
┌──────────────────┐
│  ShureService    │  service.poll_devices()
│  .poll_devices() │
└────────┬─────────┘
         │
         │ api_data
         │
         ↓
┌──────────────────────────────┐
│ DeviceLifecycleManager       │
│ .update_device_from_api()    │
│                              │
│ ┌──────────────────────────┐ │
│ │ 1. Validate transition   │ │
│ │ 2. Lock row (SELECT FOR  │ │
│ │    UPDATE)               │ │
│ │ 3. Update fields         │ │
│ │ 4. Transition state      │ │
│ │ 5. Log via StructuredLog │ │
│ │ 6. Save atomically       │ │
│ └──────────────────────────┘ │
└────────┬─────────────────────┘
         │
         ↓
┌──────────────────┐
│   Receiver       │  Updated in database
│   (Model)        │  status = 'online'
└────────┬─────────┘
         │
         │ Minimal signal
         │
         ↓
┌──────────────────┐
│ device_status_   │  WebSocket broadcast
│ changed signal   │
└────────┬─────────┘
         │
         ↓
┌──────────────────┐
│   WebSocket      │  Real-time UI update
│   Consumer       │
└──────────────────┘
```

### Push Sync (Database → API)

```
┌──────────────────┐
│   Admin UI       │  User updates name
│   or API         │
└────────┬─────────┘
         │
         │ receiver.name = 'New Name'
         │ receiver.save()
         │
         ↓
┌──────────────────┐
│  Admin Action    │  or API endpoint
│  or DRF View     │
└────────┬─────────┘
         │
         │ service.sync_device_to_api(receiver, fields=['name'])
         │
         ↓
┌──────────────────────────────┐
│ DeviceLifecycleManager       │
│ .sync_device_to_api()        │
│                              │
│ ┌──────────────────────────┐ │
│ │ 1. Get service client    │ │
│ │ 2. Build API payload     │ │
│ │ 3. HTTP PUT /devices/:id │ │
│ │ 4. Log success/failure   │ │
│ └──────────────────────────┘ │
└────────┬─────────────────────┘
         │
         ↓
┌──────────────────┐
│ Manufacturer API │  Device updated
│   (Shure)        │
└──────────────────┘
```

## Component Responsibilities

### DeviceLifecycleManager
```
┌────────────────────────────────────────┐
│     DeviceLifecycleManager             │
├────────────────────────────────────────┤
│ Responsibilities:                      │
│ • Validate state transitions           │
│ • Lock rows atomically                 │
│ • Update device models                 │
│ • Log all changes                      │
│ • Health monitoring                    │
│ • Bi-directional API sync              │
│                                        │
│ Does NOT:                              │
│ • Emit signals (except via service)    │
│ • Call APIs directly (uses service)    │
│ • Handle WebSocket (handled by signals)│
└────────────────────────────────────────┘
```

### ManufacturerService
```
┌────────────────────────────────────────┐
│       ManufacturerService              │
├────────────────────────────────────────┤
│ Responsibilities:                      │
│ • Manage API client                    │
│ • Poll devices from API                │
│ • Delegate to DeviceLifecycleManager   │
│ • Emit minimal signals for UI          │
│ • Health checks                        │
│ • Configuration management             │
│                                        │
│ Does NOT:                              │
│ • Update models directly               │
│ • Contain business logic               │
│ • Handle signal-based state management │
└────────────────────────────────────────┘
```

### Signal Handlers (Minimal)
```
┌────────────────────────────────────────┐
│        Signal Handlers                 │
├────────────────────────────────────────┤
│ Responsibilities:                      │
│ • WebSocket broadcasts                 │
│ • UI notifications                     │
│                                        │
│ Does NOT:                              │
│ • Update models                        │
│ • Validate transitions                 │
│ • Call APIs                            │
│ • Contain business logic               │
└────────────────────────────────────────┘
```

## Comparison: Before vs After

### Before: Signal Chain Complexity

```
Service
  ↓
emit_device_online()
  ↓
device_online signal
  ↓
handle_device_online()
  ├→ Find device in DB
  ├→ Update is_active
  ├→ Update last_seen
  ├→ Save
  ├→ Log via ActivityLog
  ├→ Log via StructuredLogger
  ├→ Emit another signal?
  └→ Broadcast via WebSocket

Problems:
❌ 8 steps across multiple functions
❌ Hard to test (need signal mocking)
❌ No atomicity (race conditions)
❌ No validation
❌ Debugging nightmare (signal chain)
```

### After: Direct Call Simplicity

```
Service
  ↓
mark_device_online(receiver)
  ↓
DeviceLifecycleManager.mark_online()
  ↓
DeviceLifecycleManager.transition_device()
  ├→ Validate transition (state machine)
  ├→ Lock row (SELECT FOR UPDATE)
  ├→ Update status, is_active, last_seen
  ├→ Save atomically
  ├→ Log via StructuredLogger
  └→ Emit minimal signal
      ↓
      WebSocket broadcast

Benefits:
✅ 6 steps in one function
✅ Easy to test (direct call)
✅ Atomic with locking
✅ Validated transitions
✅ Clear debugging path
```

## Usage Flow Examples

### Example 1: Polling Loop

```
┌─────────────────────────────────────────────────┐
│ 1. Scheduler triggers poll_devices              │
└─────────────┬───────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────┐
│ 2. ShureService.poll_devices()                  │
│    • Start sync log                             │
│    • Fetch devices from API                     │
└─────────────┬───────────────────────────────────┘
              │
              ↓ for each device
┌─────────────────────────────────────────────────┐
│ 3. service.update_device_from_api(receiver, api)│
│    ↓                                            │
│    DeviceLifecycleManager:                      │
│    • Map API state to lifecycle state           │
│    • Validate transition                        │
│    • Update model atomically                    │
│    • Log change                                 │
└─────────────┬───────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────┐
│ 4. service.check_device_health(receiver)        │
│    • Check last_seen timestamp                  │
│    • Auto-transition if needed                  │
│      (online → offline if timeout)              │
└─────────────┬───────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────┐
│ 5. service.emit_sync_complete()                 │
│    • Signal → WebSocket → UI notification       │
└─────────────────────────────────────────────────┘
```

### Example 2: Admin Action

```
┌─────────────────────────────────────────────────┐
│ 1. Admin clicks "Put in Maintenance"           │
└─────────────┬───────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────┐
│ 2. Admin action handler                         │
│    lifecycle = get_lifecycle_manager('shure')   │
│    for receiver in queryset:                    │
│      lifecycle.mark_maintenance(receiver, ...)  │
└─────────────┬───────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────┐
│ 3. DeviceLifecycleManager.mark_maintenance()    │
│    • Validate: online → maintenance (valid)     │
│    • Update status to 'maintenance'             │
│    • Set is_active = False                      │
│    • Log with reason                            │
│    • sync_to_api=True → push to manufacturer    │
└─────────────┬───────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────┐
│ 4. service.sync_device_to_api()                 │
│    • Build API payload: {status: 'maintenance'} │
│    • HTTP PUT to Shure System API               │
│    • Device stops alerting                      │
└─────────────┬───────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────┐
│ 5. Signal → WebSocket → UI grays out device    │
└─────────────────────────────────────────────────┘
```

### Example 3: Device Recovery

```
┌─────────────────────────────────────────────────┐
│ 1. Device offline for 2 hours                   │
│    receiver.status = 'offline'                  │
│    receiver.last_seen = 2 hours ago             │
└─────────────┬───────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────┐
│ 2. Next poll cycle                              │
│    • Device now responds                        │
│    • API returns state: 'ONLINE'                │
└─────────────┬───────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────┐
│ 3. service.update_device_from_api()             │
│    • Map 'ONLINE' → 'online'                    │
│    • Validate: offline → online (valid)         │
│    • Transition to 'online'                     │
│    • Set is_active = True                       │
│    • Update last_seen = now                     │
└─────────────┬───────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────┐
│ 4. ActivityLog records recovery                 │
│    "Receiver transitioned: offline → online"    │
└─────────────┬───────────────────────────────────┘
              │
              ↓
┌─────────────────────────────────────────────────┐
│ 5. WebSocket → Dashboard shows device green    │
└─────────────────────────────────────────────────┘
```

## Testing Architecture

### Unit Tests
```
Test: DeviceLifecycleManager
├─ test_valid_transition()
├─ test_invalid_transition()
├─ test_atomic_update()
├─ test_logging()
└─ test_health_check()

Test: ManufacturerService
├─ test_poll_devices()
├─ test_update_from_api()
├─ test_sync_to_api()
├─ test_health_monitoring()
└─ test_signal_emission()
```

### Integration Tests
```
Test: End-to-End Flow
├─ test_poll_and_update()
│  ├─ Mock API response
│  ├─ Call service.poll_devices()
│  ├─ Verify DB updated
│  └─ Check signals emitted
│
├─ test_bi_directional_sync()
│  ├─ Update model locally
│  ├─ Call sync_to_api()
│  ├─ Verify API called
│  └─ Check logs created
│
└─ test_state_recovery()
   ├─ Set device offline
   ├─ Simulate API recovery
   ├─ Poll devices
   └─ Verify auto-transition
```

## Performance Considerations

### Row Locking
```python
# Atomic update with row lock
device = Device.objects.select_for_update().get(pk=device_id)
device.status = 'online'
device.save()
```

**Impact:** Prevents race conditions during concurrent polls

### Bulk Operations
```python
# Efficient bulk health check
results = lifecycle.bulk_health_check(devices, threshold_minutes=5)
# Returns: {'online': 45, 'offline': 3, ...}
```

**Impact:** Processes 100+ devices efficiently

### Minimal Signals
```
Before: 5 signals × N devices = High overhead
After:  1 signal × N devices = Low overhead
```

**Impact:** 80% reduction in signal processing

## Summary

This architecture provides:
- ✅ **Clear separation of concerns**
- ✅ **Testable components**
- ✅ **Atomic operations**
- ✅ **Validated state machine**
- ✅ **Bi-directional sync**
- ✅ **Minimal signal usage**
- ✅ **Comprehensive logging**
- ✅ **Health monitoring**
