# Django Signals Migration Plan

**Date:** 2026-01-22
**Objective:** Replace Django signals with direct service layer calls
**Status:** Planning Phase

## Rationale

Django signals add indirection and make code flow harder to trace. Direct service calls provide:
- ✅ Explicit control flow (no hidden side effects)
- ✅ Better IDE support (jump to definition)
- ✅ Easier testing (mock service methods, not signals)
- ✅ Clear dependencies in function signatures

## Current Signal Inventory

### Request Signals (`signals/request_signals.py`)

**Purpose:** Views emit signals to trigger async operations without blocking

| Signal | Emitters | Handlers | Replacement Service |
|--------|----------|----------|---------------------|
| `discover_requested` | DiscoverAPIView | `handle_discover_requested()` | `DiscoveryService.discover_devices()` |
| `refresh_requested` | RefreshAPIView | `handle_refresh_requested()` | `PollingService.poll_devices()` |
| `device_detail_requested` | DeviceDetailAPIView | `handle_device_detail_requested()` | `ManufacturerPlugin.get_device()` |
| `add_discovery_ips_requested` | AddIPsAPIView | `handle_add_discovery_ips_requested()` | `DiscoveryService.add_discovery_candidate()` |
| `discovery_candidates_requested` | GetCandidatesView | `handle_discovery_candidates_requested()` | `DiscoveryService.get_discovery_candidates()` |

**Priority:** HIGH - These are the main signal usage in views

### Broadcast Signals (`signals/broadcast_signals.py`)

**Purpose:** Notify WebSocket layer of data changes

| Signal | Emitters | Handlers | Replacement |
|--------|----------|----------|-------------|
| `devices_polled` | PollingService, refresh handler | WebSocket consumers | Keep as event bus for WS |
| `api_health_changed` | HealthCheckService | WebSocket consumers | Keep for WS notifications |

**Priority:** LOW - Event bus pattern appropriate for pub/sub to WebSocket layer

### Device Signals (`signals/device_signals.py`)

**Purpose:** Track model lifecycle events (save/delete)

| Signal | Emitters | Handlers | Replacement |
|--------|----------|----------|-------------|
| `receiver_saved` | Receiver.save() | Cache invalidation, WS broadcast | Move to service layer save methods |
| `receiver_pre_delete` | Receiver.delete() | Cleanup before delete | Override Model.delete() |
| `receiver_deleted` | Receiver.delete() | Post-delete cleanup | Override Model.delete() |
| `channel_saved` | Channel.save() | State updates | Move to ChannelService |
| `assignment_saved` | UserAssignment.save() | Notification logic | Move to AssignmentService |

**Priority:** MEDIUM - Can be replaced with service methods

### Discovery Signals (`signals/discovery_signals.py`)

**Purpose:** Track discovery events

| Signal | Status | Notes |
|--------|--------|-------|
| Check if exists | TBD | Review file contents |

### User Signals (`signals/user_signals.py`)

**Purpose:** User profile sync

| Signal | Status | Notes |
|--------|--------|-------|
| Check if exists | TBD | Review file contents |

## Migration Strategy

### Phase 1: Request Signal Replacement (HIGH PRIORITY)

**Goal:** Remove request signal indirection in API views

#### Step 1.1: Create Direct Service Methods

Add explicit service methods matching signal handler logic:

```python
# micboard/services/discovery_service_new.py
class DiscoveryService:
    def discover_devices(
        self, *, manufacturer: str | None = None
    ) -> dict[str, dict]:
        """Discover devices across manufacturers.

        Args:
            manufacturer: Optional manufacturer code to filter

        Returns:
            Mapping of manufacturer_code -> {status, count, devices|error}
        """
        # Move logic from handle_discover_requested()
        ...

# micboard/services/polling_service.py
class PollingService:
    def refresh_devices(
        self, *, manufacturer: str | None = None
    ) -> dict[str, dict]:
        """Refresh device data and broadcast updates.

        Args:
            manufacturer: Optional manufacturer code to filter

        Returns:
            Mapping of manufacturer_code -> {status, device_count, updated}
        """
        # Move logic from handle_refresh_requested()
        ...
```

#### Step 1.2: Update API Views

Replace signal emissions with direct service calls:

**Before:**
```python
# micboard/api/v1/views/other_views.py
class RefreshAPIView(APIView):
    def post(self, request):
        manufacturer = request.data.get("manufacturer")
        result = refresh_requested.send(
            sender=self,
            manufacturer=manufacturer,
            request=request
        )
        return Response(result)
```

**After:**
```python
class RefreshAPIView(APIView):
    def post(self, request):
        manufacturer = request.data.get("manufacturer")
        polling_service = PollingService()
        result = polling_service.refresh_devices(
            manufacturer=manufacturer
        )
        return Response(result)
```

#### Step 1.3: Remove Signal Handlers

Once all emitters are updated:
1. Remove handler functions from `signals/request_signals.py`
2. Remove signal definitions
3. Remove imports from `signals/__init__.py`
4. Update tests to mock services instead of patching signals

**Files to Update:**
- `micboard/api/v1/views/other_views.py` - 5 views
- `micboard/services/discovery_service_new.py` - Add methods
- `micboard/services/polling_service.py` - Add methods
- `micboard/signals/request_signals.py` - Remove handlers
- `tests/test_api.py` - Update mocks

### Phase 2: Device Signal Replacement (MEDIUM PRIORITY)

**Goal:** Move model lifecycle logic to service layer

#### Step 2.1: Create Service Save Methods

```python
# micboard/services/receiver_service.py
class ReceiverService:
    def save_receiver(
        self, receiver: Receiver, *, invalidate_cache: bool = True
    ) -> Receiver:
        """Save receiver with side effects.

        Args:
            receiver: Receiver instance to save
            invalidate_cache: Whether to invalidate caches

        Returns:
            Saved receiver instance
        """
        receiver.save()

        if invalidate_cache:
            cache.delete(f"receiver_{receiver.id}")

        # Broadcast update
        devices_polled.send(...)

        return receiver
```

#### Step 2.2: Update Model Delete Methods

```python
# micboard/models/receiver.py
class Receiver(models.Model):
    def delete(self, *args, **kwargs):
        """Delete receiver with cleanup."""
        # Pre-delete cleanup (was receiver_pre_delete signal)
        self._cleanup_related_data()

        # Perform delete
        result = super().delete(*args, **kwargs)

        # Post-delete actions (was receiver_deleted signal)
        cache.delete(f"receiver_{self.id}")

        return result

    def _cleanup_related_data(self):
        """Clean up related data before deletion."""
        # Move handler logic here
        ...
```

#### Step 2.3: Migration Path

1. Keep signals active initially
2. Add service methods alongside signals (dual write)
3. Update code to use services
4. Verify tests pass with both
5. Remove signal handlers
6. Remove signal emissions

### Phase 3: Keep Broadcast Signals (Event Bus Pattern)

**Decision:** KEEP `broadcast_signals.py` signals

**Rationale:**
- `devices_polled` and `api_health_changed` implement pub/sub pattern
- Multiple consumers (WebSocket, cache, logging) listen independently
- Event bus is appropriate for decoupled notification
- Direct calls would require passing consumer list (tight coupling)

**Pattern:**
```python
# Service emits event
devices_polled.send(sender=self, manufacturer=m, data=data)

# Multiple independent consumers
@receiver(devices_polled)
def websocket_handler(sender, **kwargs): ...

@receiver(devices_polled)
def cache_handler(sender, **kwargs): ...

@receiver(devices_polled)
def metrics_handler(sender, **kwargs): ...
```

This is **correct usage** of Django signals: event broadcasting to decoupled consumers.

## Implementation Checklist

### ✅ Planning
- [x] Inventory all signals
- [x] Identify replacement patterns
- [x] Document migration strategy

### 🔄 Phase 1: Request Signals
- [ ] Create `DiscoveryService.discover_devices()`
- [ ] Create `PollingService.refresh_devices()`
- [ ] Create `DiscoveryService.get_device_detail()`
- [ ] Create `DiscoveryService.add_discovery_ips()`
- [ ] Create `DiscoveryService.get_discovery_candidates()`
- [ ] Update `DiscoverAPIView`
- [ ] Update `RefreshAPIView`
- [ ] Update `DeviceDetailAPIView`
- [ ] Update `AddIPsAPIView`
- [ ] Update `GetCandidatesView`
- [ ] Update tests for all views
- [ ] Remove signal handlers
- [ ] Remove signal definitions
- [ ] Verify all tests pass

### 📋 Phase 2: Device Signals
- [ ] Create `ReceiverService.save_receiver()`
- [ ] Create `ChannelService.save_channel()`
- [ ] Create `AssignmentService.save_assignment()`
- [ ] Override `Receiver.delete()`
- [ ] Update all Receiver.save() calls to use service
- [ ] Update all Channel.save() calls to use service
- [ ] Update tests
- [ ] Remove device signal handlers
- [ ] Remove device signal definitions
- [ ] Verify all tests pass

### ✅ Phase 3: Broadcast Signals
- [x] Document event bus pattern
- [x] Confirm signals should remain
- [x] Add documentation about appropriate signal usage

## Testing Strategy

### Unit Tests
- Mock service methods instead of patching signals
- Test service methods directly
- Verify return values match expected format

### Integration Tests
- Test full request flow (view -> service -> model -> broadcast)
- Verify WebSocket broadcasts still work
- Confirm cache invalidation occurs

### Migration Validation
- Run test suite after each phase
- Compare behavior before/after (logs, DB state, responses)
- Performance testing (signals had overhead)

## Rollback Plan

Each phase is independent:
1. Keep git commits small and focused
2. Tag each phase completion
3. If issues arise, revert specific phase
4. Signals and services can coexist during migration

## Timeline Estimate

| Phase | Effort | Duration |
|-------|--------|----------|
| Phase 1 (Request Signals) | High | 2-3 days |
| Phase 2 (Device Signals) | Medium | 1-2 days |
| Phase 3 (Documentation) | Low | 1 hour |
| Testing & Validation | Medium | 1 day |
| **Total** | - | **4-6 days** |

## Success Criteria

- [ ] Zero signal emitters in `micboard/api/` (except broadcast signals)
- [ ] Zero signal handlers in `signals/request_signals.py`
- [ ] All tests passing (72/72)
- [ ] Zero performance regressions
- [ ] Service layer methods have comprehensive docstrings
- [ ] Migration documented in changelog

---

**Status:** Ready to begin Phase 1
**Next Action:** Create `DiscoveryService.discover_devices()` method
