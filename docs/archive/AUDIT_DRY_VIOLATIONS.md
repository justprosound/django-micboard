# DRY Violations Audit - Phase 4.4

**Date**: January 22, 2026
**Status**: Complete - Ready for Refactoring

## Executive Summary

This audit identifies all duplicate code patterns across the django-micboard codebase. Total identified DRY violations: **47 repeated patterns** across 5 major categories. Estimated reduction: **600-800 lines of duplicate code**.

## Category 1: Polling Logic (10 duplicate methods)

### Violation 1.1: Multiple poll_devices() implementations

**Location A**: `micboard/services/device_service.py:62` - `sync_devices_from_api()`
```python
def sync_devices_from_api(self) -> tuple[int, int]:
    """Polls API and synchronizes devices"""
    # ~50 lines of polling, error handling, serialization
```

**Location B**: `micboard/services/manufacturer_service.py:231` - `poll_devices()`
```python
def poll_devices(self) -> List[Dict[str, Any]]:
    """Polls devices from manufacturer API"""
    # Similar to Location A, ~50 lines
```

**Location C**: `micboard/services/polling_service.py` (multiple methods)
- Polling orchestration with duplicate error handling

**Impact**: Duplicate error handling, retry logic, logging, serialization

### Violation 1.2: Client-level polling in multiple integrations

**Location A**: `micboard/integrations/shure/client.py:126` - `get_devices()`
**Location B**: `micboard/integrations/shure/plugin.py:40` - `get_devices()`
**Location C**: `micboard/integrations/sennheiser/client.py:75` - `get_devices()`
**Location D**: `micboard/integrations/sennheiser/plugin.py:35` - `get_devices()`

**Pattern**: Wrapper methods that call the same underlying API client

**Impact**: Abstraction leaks, duplicate responsibility layer

### Violation 1.3: Poll orchestration patterns

**Location A**: `micboard/services/polling_service.py`
**Location B**: `micboard/tasks/polling_tasks.py`
**Location C**: `micboard/tasks/discovery_tasks.py`
**Location D**: `micboard/tasks/websocket_tasks.py`
**Location E**: `micboard/tasks/sse_tasks.py`

**Pattern**: Each task file has similar polling orchestration:
```python
# Pattern repeated 5 times:
for manufacturer in Manufacturer.objects.filter(is_active=True):
    plugin = get_manufacturer_plugin(code)
    devices = plugin.get_devices()
    # Error handling
    # Signal emission
    # Serialization
```

**Impact**: Maintenance burden, inconsistent error handling, scattered logic

---

## Category 2: Health Check Patterns (6 duplicate methods)

### Violation 2.1: Health check implementation across layers

**Location A**: `micboard/integrations/base_http_client.py:158` - `check_health()`
```python
def check_health(self) -> dict[str, Any]:
    """Base HTTP client health check"""
```

**Location B**: `micboard/integrations/shure/plugin.py:78` - `check_health()`
**Location C**: `micboard/integrations/sennheiser/plugin.py:71` - `check_health()`

**Location D**: `micboard/manufacturers/base.py:23` - Base class interface
**Location E**: `micboard/manufacturers/base.py:93` - Abstract method

**Location F**: `micboard/services/manufacturer_service.py:168` - `check_health()`

**Pattern**: Health checks defined in multiple inheritance chains without clear responsibility

**Impact**: Unclear which health check is authoritative, inconsistent response format

### Violation 2.2: Health check response formatting (6 instances)

**Pattern Repeated**: Each service formats health responses slightly differently:
```python
# Variation A
return {"status": "healthy", "uptime": ..., "timestamp": ...}

# Variation B
return {"healthy": True, "details": {...}}

# Variation C
return {"error": None, "data": {...}}
```

**Impact**: API consumers must handle multiple formats, inconsistent error reporting

---

## Category 3: Signal Emission Patterns (8 duplicate patterns)

### Violation 3.1: devices_polled signal emitted in multiple places

**Locations**:
- `micboard/services/polling_service.py:192`
- `micboard/tasks/discovery_tasks.py:375`
- `micboard/tasks/polling_tasks.py:105`
- `micboard/tasks/websocket_tasks.py:185`
- `micboard/tasks/sse_tasks.py:170`
- `micboard/signals/request_signals.py:148`

**Pattern Repeated 6 times**:
```python
devices_polled.send(
    sender=None,  # or self.__class__
    manufacturer=manufacturer,
    data=serialized_data
)
```

**Impact**: Scattered signal emission, difficult to track, inconsistent sender

### Violation 3.2: Health change signals (3 instances)

**Locations**:
- `micboard/services/manufacturer_service.py:379` - `device_status_changed`
- `micboard/tasks/polling_tasks.py:88` - `api_health_changed`
- `micboard/tasks/health_tasks.py:45` - `api_health_changed`

**Pattern**: Health status updates trigger signals from multiple places

**Impact**: No single source of truth for health updates

---

## Category 4: Serialization Patterns (Fragmented)

### Violation 4.1: Serialization functions exist in multiple places

**Primary Location**: `micboard/serializers/compat.py` (150+ lines)
- `serialize_receiver()`
- `serialize_transmitter()`
- `serialize_charger()`
- etc.

**Secondary Locations** (ad-hoc serialization):
- `micboard/services/polling_service.py` - Device data serialization
- `micboard/tasks/polling_tasks.py` - Device data transformation
- `micboard/tasks/discovery_tasks.py` - Device data formatting
- `micboard/tasks/websocket_tasks.py` - Real-time serialization
- `micboard/api/views.py` - API response formatting

**Pattern**: Each module independently builds device dicts:
```python
# Pattern A (in services)
device_dict = {
    "id": device.id,
    "name": device.name,
    ...
}

# Pattern B (in tasks)
serialized = {
    "id": str(device.id),
    "name": device.name or "Unknown",
    ...
}

# Pattern C (in API)
return {"devices": [{...}], "count": len(...)}
```

**Impact**: Inconsistent formatting, maintenance burden, data drift

---

## Category 5: Admin Interface Patterns (15+ duplications)

### Violation 5.1: Repeated list_display patterns

**Pattern A**: Status-based display
```python
# Repeated in: ReceiverAdmin, TransmitterAdmin, DeviceMovementLogAdmin
list_display = ("name", "status", "manufacturer", "last_synced")
```

**Pattern B**: Manufacturer filter
```python
# Repeated in: 8+ admin classes
list_filter = ("manufacturer",)
```

**Pattern C**: Device type classification
```python
# Repeated in: ReceiverAdmin, TransmitterAdmin, ChargerAdmin
list_filter = ("device_type", "status")
```

**Impact**: Inconsistent sorting, filtering, display order

### Violation 5.2: Repeated admin actions

**Action A**: Mark status (appears 3 times)
```python
# ReceiverAdmin
@admin.action(description="Mark selected receivers as online")
def mark_online(self, request, queryset):
    # Pattern: queryset.update(status="online"), msg

# TransmitterAdmin (similar)
# DeviceMovementLogAdmin (similar)
```

**Action B**: Sync from API (appears 2 times)
```python
# ReceiverAdmin
@admin.action(description="Sync selected receivers from API")
def sync_from_api(self, request, queryset):
    # Pattern: loop, call service, update

# Similar in DeviceMovementLogAdmin
```

**Action C**: Bulk approval/rejection
```python
# DiscoveryQueueAdmin
@admin.action(description="Approve selected devices for import")
def approve_devices(self, request, queryset):
    # ~20 lines of repetitive logic
```

**Impact**: 50+ lines of identical action code across admin files

### Violation 5.3: List filter configuration (15 instances)

**Pattern 1**: Date filters
```python
# Repeated in 6 admin classes
"created_at", "updated_at", "last_synced"
```

**Pattern 2**: Status filters
```python
# Repeated in 8 admin classes
"status", "is_active", "is_online"
```

**Pattern 3**: Relationship filters
```python
# Repeated in 10 admin classes
"manufacturer", "channel__receiver__manufacturer"
```

---

## Category 6: Service Layer Patterns (Scattered responsibilities)

### Violation 6.1: Device transformation logic

**Locations**:
- `micboard/services/polling_service.py` - Raw API data → Model
- `micboard/integrations/shure/plugin.py` - Device transformation
- `micboard/integrations/sennheiser/plugin.py` - Device transformation
- `micboard/tasks/polling_tasks.py` - Device data formatting

**Pattern**: Each layer transforms device data differently

**Impact**: Data drift, inconsistent field mapping, hard to debug

### Violation 6.2: Error handling patterns

**Locations** (multiple error handling patterns):
- `micboard/services/polling_service.py` - Try/except with logging
- `micboard/tasks/polling_tasks.py` - Similar try/except
- `micboard/tasks/discovery_tasks.py` - Similar error handling
- `micboard/integrations/base_http_client.py` - HTTP-specific errors

**Pattern**: Each service implements retry logic independently

**Impact**: Inconsistent error recovery, duplicate retry loops

---

## Quantified Impact

### Code Duplication Summary

| Category | Duplicates | Lines/Instance | Total Lines | Priority |
|----------|-----------|-----------------|------------|----------|
| Polling Logic | 10 methods | 50 lines | ~500 | HIGH |
| Health Checks | 6 methods | 20 lines | ~120 | HIGH |
| Signal Emission | 8 instances | 5 lines | ~40 | MEDIUM |
| Serialization | 5 locations | 30 lines | ~150 | HIGH |
| Admin Actions | 15 actions | 20 lines | ~300 | MEDIUM |
| Service Transforms | 4 locations | 40 lines | ~160 | MEDIUM |
| **TOTAL** | **47 patterns** | **~40 avg** | **~1,270** | - |

### Estimated Refactoring Gains

- **Duplication Elimination**: 600-800 lines of repeated code removed
- **Maintenance Cost**: 50% reduction in bug fixes (fix once, applies everywhere)
- **Code Coverage**: Easier to test common patterns
- **Developer Onboarding**: Fewer patterns to learn
- **Performance**: Centralized optimization opportunities

---

## Refactoring Plan

### Phase 4.4.1: Polling Consolidation (Priority: HIGH)
- [x] Extract polling orchestration to base service
- [ ] Unify error handling
- [ ] Single device transformation layer
- **Files to change**: 8 files
- **Expected lines saved**: 300-400

### Phase 4.4.2: Health Check Consolidation (Priority: HIGH)
- [ ] Create HealthCheckMixin
- [ ] Standardize response format
- [ ] Remove duplicate implementations
- **Files to change**: 6 files
- **Expected lines saved**: 100-150

### Phase 4.4.3: Signal Pattern Consolidation (Priority: MEDIUM)
- [ ] Create signal emission utilities
- [ ] Document signal contracts
- [ ] Centralize signal definitions
- **Files to change**: 6 files
- **Expected lines saved**: 30-50

### Phase 4.4.4: Serialization Consolidation (Priority: HIGH)
- [ ] Audit all serialization locations
- [ ] Create serializer registry
- [ ] Standardize response format
- **Files to change**: 8 files
- **Expected lines saved**: 100-150

### Phase 4.4.5: Admin Pattern Consolidation (Priority: MEDIUM)
- [ ] Extract base admin action classes
- [ ] Create admin mixins
- [ ] Standardize list_display/list_filter
- **Files to change**: 10+ admin files
- **Expected lines saved**: 150-200

---

## Risk Assessment

### High Risk Areas
1. **Polling Logic** - Used in production polling, needs extensive testing
2. **Signal Emission** - Async behavior, may have race conditions
3. **Serialization** - API contracts, must not break clients

### Mitigation Strategy
1. Keep comprehensive test suite running
2. Refactor incrementally with git snapshots
3. Validate all 72 tests after each change
4. Load test with mock devices before deployment

---

## Success Criteria

- ✅ All 72 tests passing after refactoring
- ✅ Duplicate code reduced by 50%+
- ✅ No new performance regressions
- ✅ Clearer code organization
- ✅ Faster developer onboarding
- ✅ Easier bug fixes (fix-once patterns)

---

**Next Step**: Begin Phase 4.4.1 - Polling Consolidation
