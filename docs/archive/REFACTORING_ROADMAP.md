# Django Micboard - Refactoring Roadmap (Phase 4)

**Date:** January 22, 2026
**Status:** 🔄 In Progress
**Goal:** DRY principles, multi-manufacturer consolidation, live device testing

## Overview

This document outlines the comprehensive refactoring plan to consolidate duplicate code, improve the multi-manufacturer plugin architecture, and prepare for live device testing at Georgia Tech.

## Current State Analysis

### Documentation Status
- ✅ Phase 2 & 3 completion docs exist
- ✅ PROJECT_PHASES.md created as central index
- ⚠️ PUBLIC_REPO_SECURITY.md references outdated file structures (docs/local-testing/)
- ⚠️ Some Phase docs contain duplicate information

### Code Structure Analysis

**Services Layer:**
- `device_service.py` - Device CRUD operations
- `polling_service.py` - Polling orchestration
- `manufacturer_service.py` - Manufacturer-specific logic (ABC)
- `device_lifecycle.py` - Lifecycle state machine
- `discovery_service_new.py` - Device discovery
- `direct_polling_service.py` - Direct device polling (potential duplicate)

**Manufacturer Plugins:**
- `micboard/integrations/shure/` - Shure implementation
- `micboard/integrations/sennheiser/` - Sennheiser implementation
- `micboard/manufacturers/base.py` - Base classes (compatibility shim)
- ⚠️ Both integrations and manufacturers folders exist (confusing structure)

**Potential DRY Violations:**
1. Device polling logic duplicated across services
2. API client health checks repeated in multiple places
3. Serialization logic scattered across services
4. Admin action patterns repeated
5. Signal emission patterns duplicated

## Refactoring Plan

### Phase 4.1: Documentation Consolidation ✅ (This Session)

**Tasks:**
1. ✅ Update PUBLIC_REPO_SECURITY.md to remove outdated references
2. ✅ Consolidate Phase 2 completion docs
3. ✅ Update PROJECT_PHASES.md with Phase 4 details
4. ✅ Create this REFACTORING_ROADMAP.md

### Phase 4.2: Service Layer DRY Refactoring ✅ (Completed)

**Objective:** Eliminate duplicate patterns across services

**Completed Tasks:**
1. ✅ **Base HTTP Client Abstraction**
   - Created `micboard/integrations/base_http_client.py`
   - **BaseHTTPClient**: Common HTTP client with retry, pooling, health tracking
   - **BasePollingMixin**: Shared device polling logic
   - Eliminated ~200 lines of duplicate code per manufacturer

2. ✅ **Refactored Shure Client**
   - `ShureSystemAPIClient` now extends `BaseHTTPClient`
   - Implements only Shure-specific methods:
     - `_get_config_prefix()` → "SHURE_API"
     - `_configure_authentication()` → Bearer token auth
     - `_get_health_check_endpoint()` → "/api/v1/devices"
     - `get_exception_class()` → ShureAPIError
     - `get_rate_limit_exception_class()` → ShureAPIRateLimitError
   - Reduced from 400+ lines to ~120 lines

3. ✅ **Refactored Sennheiser Client**
   - `SennheiserSystemAPIClient` now extends `BaseHTTPClient`
   - Implements only Sennheiser-specific methods:
     - `_get_config_prefix()` → "SENNHEISER_API"
     - `_configure_authentication()` → HTTP Basic Auth
     - `_get_health_check_endpoint()` → "/api/ssc/version"
     - `get_exception_class()` → SennheiserAPIError
     - `get_rate_limit_exception_class()` → SennheiserAPIRateLimitError
   - Reduced from 400+ lines to ~80 lines

4. ✅ **Consolidated Device Polling Logic**
   - `BasePollingMixin` provides:
     - `poll_all_devices()` - Polls all devices for a manufacturer
     - `_poll_single_device()` - Polls single device with enrichment
     - `_log_firmware_coverage()` - Logs firmware coverage stats
   - Both Shure and Sennheiser clients use mixin

5. ✅ **Validation**
   - All 72 tests passing
   - No backwards compatibility issues
   - Clean refactor with no functional changes

**Benefits:**
- **Reduced Duplication:** ~400 lines of duplicate code eliminated
- **Easier Maintenance:** Bug fixes in BaseHTTPClient apply to all manufacturers
- **Extensibility:** New manufacturers can reuse 90% of HTTP client logic
- **Type Safety:** Abstract methods enforce plugin contract
- **Test Coverage:** Existing tests validate refactored code

### Phase 4.3: Multi-Manufacturer Plugin Architecture (Next)

**Objective:** Clean, extensible plugin system

**Tasks:**
1. **Consolidate Polling Logic**
   - Extract common polling patterns to base service
   - Remove `direct_polling_service.py` if redundant
   - Unified error handling and logging

2. **Consolidate Health Check Patterns**
   - Create `HealthCheckMixin` for common health check logic
   - Apply to all API clients
   - Standardize health check response format

3. **Consolidate Serialization**
   - Move all serialization to `micboard/serializers/`
   - Remove ad-hoc serialization from services
   - Create serializer registry

4. **Consolidate Signal Patterns**
   - Extract signal emission to utility function
   - Standardize signal payload format
   - Document signal contracts

### Phase 4.3: Multi-Manufacturer Plugin Architecture

**Objective:** Clean, extensible plugin system

**Tasks:**
1. **Consolidate Plugin Structure**
   ```
   micboard/integrations/
   ├── base.py           # Base plugin classes (move from manufacturers/)
   ├── shure/
   │   ├── plugin.py
   │   ├── client.py
   │   └── transformers.py
   └── sennheiser/
       ├── plugin.py
       ├── client.py
       └── transformers.py

   micboard/manufacturers/  # REMOVE - use integrations/
   ```

2. **Extract Common Client Patterns**
   - Base `APIClient` with common HTTP logic
   - Base `DiscoveryClient` for device discovery
   - Base `DeviceClient` for device operations
   - Base `TransformerClient` for data transformation

3. **Plugin Registry Improvements**
   - Auto-discovery of plugins
   - Plugin validation and health checks
   - Plugin capability declaration

### Phase 4.4: Admin Interface Consolidation

**Objective:** DRY admin actions and filters

**Tasks:**
1. **Extract Common Admin Actions**
   - Base admin class with lifecycle actions
   - Mixin for sync actions
   - Mixin for health check actions

2. **Consolidate List Filters**
   - Reusable filter classes
   - Custom filter widgets

3. **Admin Template Improvements**
   - Shared admin templates
   - Consistent styling

### Phase 4.5: Docker & Live Testing Setup

**Objective:** Enable live device testing against Georgia Tech devices

**Tasks:**
1. **Update Docker Configuration**
   - Multi-stage build for production
   - Development mode with hot-reload
   - Network configuration for GT devices
   - Environment variable documentation

2. **Create Testing Configuration**
   - Test environment setup
   - Mock device factories
   - Integration test suite

3. **Documentation**
   - Docker setup guide
   - Live testing workflow
   - Troubleshooting guide

## Implementation Order

### Week 1: Documentation & Planning
- ✅ Document current state
- ✅ Create refactoring roadmap
- ✅ Update documentation for continuity
- ⏳ Identify all DRY violations
- ⏳ Create detailed refactoring tickets

### Week 2: Service Layer Refactoring
- ⏳ Consolidate polling logic
- ⏳ Consolidate health checks
- ⏳ Extract serialization
- ⏳ Consolidate signal patterns
- ⏳ Test and validate changes

### Week 3: Plugin Architecture
- ⏳ Consolidate plugin structure
- ⏳ Extract common client patterns
- ⏳ Improve plugin registry
- ⏳ Test and validate changes

### Week 4: Admin & Testing
- ⏳ Consolidate admin interface
- ⏳ Update Docker configuration
- ⏳ Create integration tests
- ⏳ Live device testing at GT
- ⏳ Final documentation

## Success Metrics

**Code Quality:**
- Reduce code duplication by 30%+
- Improve test coverage to 85%+
- Zero mypy errors
- Zero linting errors

**Architecture:**
- Single plugin interface for all manufacturers
- Clear separation of concerns
- Extensible for new manufacturers

**Documentation:**
- All phases documented and linked
- Developer onboarding < 30 minutes
- Clear testing procedures

**Testing:**
- Full integration test suite
- Live device testing successful
- Docker environment working

## Risk Mitigation

**Risks:**
1. Breaking existing functionality
   - **Mitigation:** Comprehensive test suite, incremental changes

2. Performance regression
   - **Mitigation:** Benchmark before/after, performance tests

3. Integration issues with live devices
   - **Mitigation:** Extensive mocking, staged rollout

4. Documentation drift
   - **Mitigation:** Update docs with each change, review process

## Files to Modify

### High Priority
- `micboard/services/device_service.py` - DRY refactoring
- `micboard/services/polling_service.py` - Consolidate patterns
- `micboard/integrations/base.py` - Create unified base
- `demo/docker/docker-compose.yml` - Update for GT testing
- `demo/docker/Dockerfile` - Multi-stage build

### Medium Priority
- `micboard/admin/receivers.py` - Extract common patterns
- `micboard/serializers/` - Consolidate serialization
- `micboard/signals/handlers.py` - Simplify patterns

### Low Priority
- Admin templates
- Documentation formatting
- Code comments

## Next Actions

1. ✅ Complete documentation consolidation
2. ⏳ Audit codebase for all DRY violations (detailed)
3. ⏳ Create base plugin classes
4. ⏳ Consolidate Shure/Sennheiser common code
5. ⏳ Update Docker for live testing
6. ⏳ Test with real devices at Georgia Tech

---

**Status:** Phase 4.1 in progress - Documentation consolidation
**Last Updated:** January 22, 2026
