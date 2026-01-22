# Django-Micboard Refactoring: Phase 3 - Services & Configuration

## Overview

This phase refactors django-micboard to:
1. **Update to Django 5.1.x** for future compatibility
2. **Services-focused architecture** for manufacturer integrations
3. **Configuration management** with admin UI for overrides/validation

## Current State

- Django version: 4.2+ with support for 5.0, 5.1
- Manufacturer architecture: Plugin-based in `micboard.integrations`
- Services: Basic services layer exists in `micboard.services`
- Configuration: Environment variables and settings.py

## Target State

### 1. Django 5.1.x Compatibility
- Update pyproject.toml to require Django 5.1.x
- Run full test suite against 5.1.x
- Update deprecation warnings from Django 5.0
- Test channels/ASGI compatibility

### 2. Services-Focused Architecture

**Current Flow:**
```
Plugin → Client → API
```

**New Flow:**
```
ManufacturerService ↓
├─ APIClient ↓
├─ SignalHandlers ↓
└─ TaskQueue
```

### 3. Configuration Management

**Before:**
```python
# settings.py
MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": os.environ.get("..."),
    "SHURE_API_SHARED_KEY": os.environ.get("..."),
}
```

**After:**
```python
# Django admin UI
ManufacturerConfiguration (model)
├─ Code (shure, sennheiser)
├─ Name (display name)
├─ IsActive (enable/disable)
├─ Config (JSON field)
├─ LastValidated (timestamp)
└─ ValidationErrors (JSON)
```

## Implementation Steps

### Step 1: Update Django to 5.1.x
- [ ] Update pyproject.toml
- [ ] Run: pip install -e .[dev]
- [ ] Run: pytest tests/
- [ ] Fix deprecation warnings
- [ ] Update GitHub classifiers

### Step 2: Refactor Manufacturer Services
- [ ] Create `ManufacturerService` abstract base
- [ ] Create `ManufacturerServiceConfig` container
- [ ] Create `ServiceRegistry` for management
- [ ] Migrate Shure plugin → ShureService
- [ ] Add signal definitions for device lifecycle
- [ ] Add task definitions for async polling

### Step 3: Configuration Management System
- [ ] Create `ManufacturerConfiguration` model
- [ ] Add `ConfigurationValidator` class
- [ ] Create admin interface for configs
- [ ] Implement admin actions (test, reload, validate)
- [ ] Create settings override mechanism

### Step 4: Signals & Lifecycle Events
- [ ] Define Django signals:
  - `device_discovered`
  - `device_online`
  - `device_offline`
  - `device_updated`
- [ ] Connect handlers in `micboard/signals/`
- [ ] Emit signals from services

### Step 5: Async Task Queue
- [ ] Refactor polling as scheduled tasks
- [ ] Add task logging and monitoring
- [ ] Implement retry logic with backoff
- [ ] Add task cancellation support

## Benefits

1. **Maintainability**: Clear separation of concerns
2. **Extensibility**: Easy to add new manufacturers
3. **Configurability**: Admin UI for runtime config changes
4. **Observability**: Signals enable monitoring and alerting
5. **Async**: Non-blocking polling and discovery
6. **Future-proof**: Django 5.1.x compatibility

## Related Files

- `pyproject.toml` - Dependencies
- `micboard/services/` - Service implementations
- `micboard/models/` - Database models
- `micboard/admin/` - Admin interface
- `micboard/signals/` - Event handlers
- `micboard/tasks/` - Background jobs
- `micboard/integrations/` - Manufacturer API clients

## Testing Strategy

1. Unit tests for each service
2. Integration tests for signal flow
3. Admin interface tests
4. Configuration validation tests
5. Backwards compatibility tests
6. Performance tests for polling

## Migration Path

- Phase 3a: Django 5.1.x update (non-breaking)
- Phase 3b: Services refactoring (backwards compatible)
- Phase 3c: Configuration management (new feature)
- Phase 3d: Signals & events (new feature)
- Phase 3e: Async task queue (new feature)

## Estimated Effort

- Django update: 1-2 hours
- Services refactoring: 4-6 hours
- Config system: 3-4 hours
- Signals: 2-3 hours
- Task queue: 2-3 hours
- Testing: 3-4 hours

**Total: 15-22 hours**

## Success Criteria

✓ Tests pass on Django 5.1.x
✓ All manufacturer services ported
✓ Configuration UI functional
✓ Signals emit correctly
✓ Polling works via tasks
✓ Backwards compatibility maintained
✓ Documentation updated

---

**Status**: Planning  
**Target Date**: Jan 21-22, 2026  
**Owner**: AI Agent
