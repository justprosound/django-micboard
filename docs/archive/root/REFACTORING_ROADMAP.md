# Refactoring Roadmap - Django Micboard

## Phase 1: Service Layer & Manager Enhancements (Current Focus)

### 1.1 Move Signal Logic to Services
**Current State:**
- `device_signals.py` - Contains post_save/pre_delete hooks with core logic
- `request_signals.py` - Handles discovery, refresh, detail requests with full business logic
- `discovery_signals.py` - Schedules discovery tasks

**Issues:**
- Business logic in signals makes it hard to test
- Difficult to reuse logic without triggering signals
- Signal handlers can fail silently
- Tight coupling to Django signals

**Solution:**
- Create `DeviceSyncService` for sync operations
- Create `DiscoveryOrchestrationService` for discovery workflows
- Keep signals minimal: only for broadcast/logging
- Signals call services, not vice versa

### 1.2 Enhance Existing Managers
**Current State:**
- `ReceiverManager` - Good filtering but needs tenant awareness
- `TransmitterManager` - Basic filtering
- `ChargerManager` - Minimal methods
- Managers have limited composability

**Solution:**
- Add `.for_organization()`, `.for_campus()`, `.for_site()` to all managers
- Create QuerySet methods that can be chained
- Add `.with_latest_status()` for optimization
- Ensure all managers use `TenantAwareManager` as base

### 1.3 Decouple DRF from Models
**Current State:**
- Serializers have `.get_*` methods in models
- Models have properties that import services (`uptime_summary`, etc.)
- Tight coupling between models and API layer

**Solution:**
- Move computed properties to serializer methods
- Use `SerializerMethodField` consistently
- Create DTO layer for complex computations
- Models should be data-only (no computation)

## Phase 2: Query Optimization & Caching

### 2.1 Add Database Indexes
- Index on `(organization_id, status)` for receivers
- Index on `(campus_id, is_active)` for buildings
- Index on `(manufacturer_id, last_seen)` for sync operations

### 2.2 Implement Select/Prefetch Related
- Receivers → Manufacturer, Location, Building
- Channels → Receiver, Transmitters
- Chargers → Slots, ChargerSlots with transmitters

## Phase 3: Type Hints & Documentation

### 3.1 Complete Type Coverage
- Add return type hints to all manager methods
- Add type hints to QuerySet filter chains
- Document service contracts with return type unions

### 3.2 Docstring Standards
- All public methods need docstrings
- Include examples for complex methods
- Document side effects clearly

## Phase 4: Error Handling & Validation

### 4.1 Custom Exceptions
- `DiscoveryError` for discovery failures
- `SyncError` for sync operation failures
- `DeviceNotFoundError` for missing devices
- `UnauthorizedAccessError` for tenant violations

### 4.2 Validation Layer
- Move complex validation to services
- Use form validation for inputs
- Sanitize user inputs at service layer

## Implementation Order

1. ✅ Add `micboard.multitenancy` module (DONE)
2. 🔲 Create service layer for discovery & sync
3. 🔲 Minimize signals (audit-only)
4. 🔲 Enhance managers with tenant filtering
5. 🔲 Decouple DRF from models
6. 🔲 Add type hints throughout
7. 🔲 Create DTOs for complex data
8. 🔲 Performance optimization (indexes, prefetch)

## Success Criteria

- ✅ All signals are audit-only
- ✅ Services handle all business logic
- ✅ Managers have `.for_organization()`, `.for_campus()`, `.for_site()`
- ✅ Models have no service imports
- ✅ Serializers don't reach into models for computation
- ✅ 100% type hints on public APIs
- ✅ All errors explicitly handled
- ✅ Backward compatible with single-site mode
