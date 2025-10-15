# Django Micboard Refactoring Plan

## Overview
This document outlines the planned refactoring to improve code organization, maintainability, and DRY principles for django-micboard as a reusable Django app compatible with Django 4.2+ and 5+.

## Current State Analysis

### Large Files Identified
1. **shure_api_client.py** (664 lines) - HTTP/WebSocket client with data transformation
2. **management/commands/poll_devices.py** (449 lines) - Polling logic with serialization
3. **models/devices.py** (393 lines) - Multiple model definitions
4. **views/api.py** (348 lines) - Multiple API endpoints
5. **models/assignments.py** (320 lines) - Assignment and alert models
6. **admin.py** (310 lines) - All admin configurations

### DRY Violations Found
- ✅ **FIXED**: Duplicate serialization in `views/api.py` and `poll_devices.py`
  - Created `micboard/serializers.py` with reusable serialization functions
  - Functions use keyword-only parameters for clarity (Django 4.2+/5+ compatible)
  - Centralized: `serialize_transmitter()`, `serialize_channel()`, `serialize_receiver()`, etc.

## Completed Refactorings

### 1. Serializers Module ✅
**File**: `micboard/serializers.py`

**Purpose**: Centralize all data serialization logic

**Functions**:
- `serialize_transmitter(transmitter, *, include_extra=False)` - Serialize transmitter data
- `serialize_channel(channel, *, include_extra=False)` - Serialize channel with optional transmitter
- `serialize_receiver(receiver, *, include_extra=False)` - Serialize full receiver hierarchy
- `serialize_receivers(receivers=None, *, include_extra=False)` - Batch serialize receivers
- `serialize_discovered_device(device)` - Serialize discovered devices
- `serialize_group(group)` - Serialize monitoring groups
- `serialize_receiver_summary(receiver)` - Lightweight receiver info for lists
- `serialize_receiver_detail(receiver)` - Full receiver detail with computed properties

**Benefits**:
- Single source of truth for serialization logic
- Consistent data structures across API and WebSocket
- Easy to test and maintain
- Keyword-only parameters prevent boolean confusion
- Type hints for better IDE support

**Updated Files**:
- `micboard/views/api.py` - Now uses serializers
- `micboard/management/commands/poll_devices.py` - Now uses serializers

## Proposed Refactorings

### 2. Split shure_api_client.py (664 lines)

**Current Structure**:
- HTTP client methods (GET, POST, device queries)
- WebSocket connection and subscription logic
- Data transformation (_transform_device_data, _transform_transmitter_data)
- Device type mapping
- Health tracking
- Connection pooling setup

**Proposed Split**:

#### File: `micboard/shure/client.py` (~300 lines)
```python
"""Base HTTP client for Shure System API"""
class ShureSystemAPIClient:
    - __init__() with connection pooling
    - _make_request() with retry logic
    - Health tracking (is_healthy, check_health, etc.)
    - Basic CRUD: get_devices(), get_device_by_id(), poll_all_devices()
```

#### File: `micboard/shure/transformers.py` (~200 lines)
```python
"""Data transformation utilities for Shure API responses"""
- _map_device_type()
- _transform_device_data()
- _transform_transmitter_data()
- _enrich_device_data()
- _format_runtime()
- identify_device_model()
```

#### File: `micboard/shure/websocket.py` (~150 lines)
```python
"""WebSocket connection handler for Shure System API"""
- connect_and_subscribe()
- WebSocket-specific logic
- Subscription management
```

#### File: `micboard/shure/__init__.py`
```python
"""Public API for Shure System API integration"""
from .client import ShureSystemAPIClient
from .transformers import identify_device_model

__all__ = ["ShureSystemAPIClient", "identify_device_model"]
```

**Benefits**:
- Easier to test individual components
- Clear separation of concerns
- Simpler to add new API endpoints
- WebSocket logic isolated for maintenance

### 3. Split admin.py (310 lines)

**Proposed Structure**:

#### File: `micboard/admin/device_admin.py`
```python
"""Admin configurations for device models"""
- ReceiverAdmin
- ChannelAdmin
- TransmitterAdmin
- DiscoveredDeviceAdmin
- GroupAdmin
```

#### File: `micboard/admin/assignment_admin.py`
```python
"""Admin configurations for assignment and alert models"""
- DeviceAssignmentAdmin
- UserAlertPreferenceAdmin
- AlertAdmin
```

#### File: `micboard/admin/monitoring_admin.py`
```python
"""Admin configurations for location and monitoring models"""
- LocationAdmin
- MonitoringGroupAdmin
- MicboardConfigAdmin
```

#### File: `micboard/admin/__init__.py`
```python
"""Register all admin configurations"""
# Import all admin classes to trigger registration
from .assignment_admin import *
from .device_admin import *
from .monitoring_admin import *
```

**Benefits**:
- Logical grouping by functionality
- Easier to find and modify admin configurations
- Better for team collaboration
- Follows Django best practices for larger apps

### 4. Split views/api.py (348 lines)

**Proposed Structure**:

#### File: `micboard/views/api/data_views.py`
```python
"""Data retrieval API endpoints"""
- data_json() - Main data endpoint with caching
```

#### File: `micboard/views/api/management_views.py`
```python
"""Device and configuration management endpoints"""
- ConfigHandler (CBV for config updates)
- GroupUpdateHandler (CBV for group updates)
- api_discover() - Trigger device discovery
- api_refresh() - Force data refresh
```

#### File: `micboard/views/api/health_views.py`
```python
"""Health and monitoring endpoints"""
- api_health() - API and Shure System health check
- api_receiver_detail() - Detailed receiver info
- api_receivers_list() - List all receivers
```

#### File: `micboard/views/api/mixins.py`
```python
"""Reusable view mixins for DRY"""
class JSONResponseMixin:
    """Helper for consistent JSON responses"""
    
class ErrorHandlingMixin:
    """Consistent error handling across views"""
    
class CacheableMixin:
    """Cache support for API views"""
```

#### File: `micboard/views/api/__init__.py`
```python
"""Public API for micboard API views"""
from .data_views import data_json
from .health_views import api_health, api_receiver_detail, api_receivers_list
from .management_views import (
    ConfigHandler,
    GroupUpdateHandler,
    api_discover,
    api_refresh,
)

__all__ = [
    "data_json",
    "api_health",
    "api_receiver_detail",
    "api_receivers_list",
    "ConfigHandler",
    "GroupUpdateHandler",
    "api_discover",
    "api_refresh",
]
```

**Benefits**:
- Clear functional separation
- Easier to add new endpoints
- Mixins promote DRY for common patterns
- Better organization for API documentation

### 5. Additional DRY Opportunities

#### Error Handling Decorator
Create `micboard/views/decorators.py`:
```python
def api_error_handler(func):
    """Decorator for consistent error handling in API views"""
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        try:
            return func(request, *args, **kwargs)
        except ObjectDoesNotExist:
            return JsonResponse({"error": "Not found"}, status=404)
        except ValidationError as e:
            return JsonResponse({"error": "Validation error", "detail": str(e)}, status=400)
        except Exception as e:
            logger.exception(f"Error in {func.__name__}: {e}")
            return JsonResponse({"error": "Internal server error", "detail": str(e)}, status=500)
    return wrapper
```

#### QuerySet Methods
Add common querysets to model managers:
```python
# In ReceiverManager
def with_channel_data(self):
    """Prefetch channels and transmitters for efficient queries"""
    return self.prefetch_related("channels__transmitter")

def active_with_health(self):
    """Get active receivers with health data"""
    return self.active().with_channel_data()
```

## Django 4.2+ and 5+ Compatibility

### Keyword-Only Parameters
All boolean parameters in new code use keyword-only syntax:
```python
def my_function(obj, *, include_extra: bool = False):  # ✅ Good
    pass

def my_function(obj, include_extra: bool = False):  # ❌ Avoid
    pass
```

### Type Hints
Using modern Python type hints compatible with Python 3.9+:
```python
from __future__ import annotations
from typing import TYPE_CHECKING, Any

def serialize_receiver(receiver: Receiver, *, include_extra: bool = False) -> dict[str, Any]:
    ...
```

### Async/Await Support
WebSocket handlers already use async/await, which is fully supported in both Django 4.2 and 5.

### No Deprecated APIs
- Avoided `django.utils.six` (removed in Django 4.0)
- Using `GenericIPAddressField` (not deprecated `IPAddressField`)
- Using `JSONField` from `django.db.models` (not contrib.postgres)

## Testing Strategy

### Unit Tests
- Test each serializer function independently
- Test mixins with mock views
- Test transformers with sample API data

### Integration Tests
- Ensure serialized data matches expected structure
- Test API endpoints return correct data
- Verify WebSocket broadcasts work

### Compatibility Tests
- Test against Django 4.2.x
- Test against Django 5.0+
- Test against Python 3.9, 3.10, 3.11, 3.12, 3.13

## Implementation Priority

1. ✅ **DONE**: Create serializers module and update views
2. **High**: Split shure_api_client.py (largest file, complex logic)
3. **Medium**: Split admin.py (improves discoverability)
4. **Medium**: Split views/api.py (clearer API structure)
5. **Low**: Create view mixins (nice-to-have for DRY)

## Migration Path

### For Existing Installations
All changes are backward compatible:
- Imports from `micboard.shure_api_client` will still work (re-exports)
- Imports from `micboard.admin` will still work (package init imports all)
- Imports from `micboard.views.api` will still work (package init exports all)
- No database migrations needed

### Documentation Updates Needed
- Update README.md with new module structure
- Update API documentation with new endpoint organization
- Add examples using new serializer functions
- Document admin organization for customization

## File Size Goals

| Current File | Current Lines | Target Lines | Strategy |
|-------------|---------------|--------------|----------|
| shure_api_client.py | 664 | ~300 | Split into client/transformers/websocket |
| admin.py | 310 | ~100/file | Split into device/assignment/monitoring |
| views/api.py | 348 | ~100/file | Split into data/management/health |
| poll_devices.py | 449 | ~400 | Use serializers (already done) |

## Success Criteria

- ✅ No duplicate serialization logic
- All files under 400 lines
- Clear module boundaries
- All existing tests pass
- Django 4.2+ and 5+ compatibility maintained
- No breaking changes to public API
- Documentation updated
