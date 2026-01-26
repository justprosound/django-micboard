# Phase 2: Code Consolidation & Performance Optimization

**Status:** In Progress
**Version:** 26.01.22
**Session Date:** January 22, 2026

## Overview

Phase 2 focuses on DRY principle enforcement and performance optimization following Phase 1's signal migration completion. This phase addresses code duplication, consolidates shared utilities, and improves caching strategies.

## Identified Duplications

### 1. **Rate Limiter Implementation** 🎯
**Status:** IDENTIFIED - Ready for consolidation

**Files:**
- `micboard/integrations/shure/rate_limiter.py`
- `micboard/integrations/sennheiser/rate_limiter.py`

**Issue:** Identical rate limiting implementation in both vendor integrations (44 lines each)

**Solution:** Create shared `micboard/integrations/common/rate_limiter.py`
- Extract to base module
- Both vendors import and use the same decorator
- Expected savings: ~44 lines of duplicate code

### 2. **Exception Base Classes** 🎯
**Status:** IDENTIFIED - Partially duplicated

**Files:**
- `micboard/integrations/shure/exceptions.py` (48 lines)
- `micboard/integrations/sennheiser/exceptions.py` (23 lines)

**Issue:** Similar exception hierarchy with minor differences

**Solution:** Create shared base exception classes
- `APIError` - Base class for all API errors
- `APIRateLimitError` - Specific rate limiting exception
- Allow vendor-specific subclasses for customization
- Expected savings: ~30 lines of duplicate code

### 3. **Vendor Utils/Utils Files** 🔍
**Status:** NEEDS AUDIT

**Files:**
- `micboard/integrations/shure/utils.py`
- `micboard/integrations/sennheiser/utils.py`

**Action:** Review for utility function duplication

## Code Consolidation Plan

### Phase 2.1: Extract Common Rate Limiting (Week 1)
```
✅ Create micboard/integrations/common/rate_limiter.py
✅ Import and use in both vendor modules
✅ Update tests to use shared implementation
✅ Verify no regressions (102 tests still passing)
```

### Phase 2.2: Consolidate Exception Handling (Week 1)
```
✅ Create micboard/integrations/common/exceptions.py
✅ Define base exception hierarchy
✅ Update vendor modules to inherit from base
✅ Verify exception behavior unchanged
```

### Phase 2.3: Audit Utils Functions (Week 2)
```
- Review shure/utils.py for reusable functions
- Review sennheiser/utils.py for reusable functions
- Extract common utilities to common/utils.py
- Update vendor imports
```

### Phase 2.4: Performance Optimization (Week 2-3)
```
- Implement device data caching layer
- Add polling result caching
- Optimize database queries
- Add monitoring metrics
```

## Performance Improvements

### 1. **Device Data Caching**
**Goal:** Reduce API calls by 50%

**Implementation:**
```python
# Cache device list for 30 seconds between polls
cache_key = f"devices_{manufacturer_code}"
devices = cache.get(cache_key)
if not devices:
    devices = api_client.get_devices()
    cache.set(cache_key, devices, timeout=30)
```

**Expected Impact:**
- Reduces API calls from 120/hour to ~60/hour
- Faster discovery operations
- Lower network bandwidth usage

### 2. **Query Optimization**
**Goal:** Reduce database queries by 30%

**Implementation:**
- Use `select_related()` for ForeignKey relationships
- Use `prefetch_related()` for reverse relationships
- Add database indexes on frequently queried fields

**Example:**
```python
receivers = Receiver.objects.filter(
    online=True
).select_related(
    'manufacturer', 'location'
).prefetch_related(
    'channels'
)
```

### 3. **Polling Efficiency**
**Goal:** Reduce polling time by 20%

**Implementation:**
- Only update changed fields
- Batch database updates
- Skip unchanged devices
- Use `bulk_update()` for multiple devices

## Testing Strategy

### Regression Testing
- All 102 existing tests must pass
- New consolidation tests added for shared utilities
- Performance benchmarks established

### Test Additions
```python
# Tests for common rate limiter
test_rate_limit_shared_implementation()
test_rate_limit_different_vendors()
test_rate_limit_concurrent_calls()

# Tests for common exceptions
test_base_api_error_inheritance()
test_vendor_specific_exceptions()
test_rate_limit_retry_after()
```

## Metrics & Goals

### Code Quality
| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Code duplication | ~100 lines | 10 lines | 🎯 In Progress |
| Test coverage | 100% | 100% | ✅ Maintained |
| Linting errors | 0 | 0 | ✅ Maintained |
| Type hints | 95% | 100% | 🎯 Improving |

### Performance
| Metric | Current | Target | Improvement |
|--------|---------|--------|------------|
| Polling time | 12s (20 devices) | 9.6s | 20% faster |
| API calls/hour | 120 | 60 | 50% less |
| DB queries/poll | 45 | 30 | 33% fewer |
| Memory usage | baseline | -10% | Cache efficiency |

## Timeline

### Week 1: Consolidation
- ✅ Extract rate limiter (Day 1-2)
- ✅ Consolidate exceptions (Day 2-3)
- ✅ Update vendor modules (Day 3-4)
- ✅ Regression testing (Day 4-5)

### Week 2-3: Performance
- Cache implementation (Day 1-3)
- Query optimization (Day 3-4)
- Polling improvements (Day 4-5)
- Performance benchmarking (Day 5)

## Files to Create/Modify

### Create
- `micboard/integrations/common/__init__.py`
- `micboard/integrations/common/rate_limiter.py`
- `micboard/integrations/common/exceptions.py`
- `micboard/integrations/common/utils.py` (if needed)
- `micboard/tests/test_common_rate_limiter.py`
- `micboard/tests/test_common_exceptions.py`

### Modify
- `micboard/integrations/shure/rate_limiter.py` → import from common
- `micboard/integrations/sennheiser/rate_limiter.py` → import from common
- `micboard/integrations/shure/exceptions.py` → inherit from common
- `micboard/integrations/sennheiser/exceptions.py` → inherit from common
- `micboard/integrations/shure/device_client.py` → update imports
- `micboard/integrations/sennheiser/device_client.py` → update imports

## Success Criteria

✅ **Consolidation:**
- All duplicate code eliminated
- 90+ lines of code removed
- Zero regressions (102 tests passing)
- No performance degradation

✅ **Performance:**
- 20% reduction in polling time
- 50% reduction in API calls
- 33% reduction in database queries
- Memory usage within 10% of baseline

✅ **Quality:**
- Type hints 100% complete
- Zero linting errors
- Comprehensive test coverage
- Full documentation updated

## Related Issues & PRs

- Phase 1 Completion: Signal migration ✅
- Phase 1 Testing: Shure API tests (30 tests) ✅
- Phase 2 Consolidation: This document 🎯
- Phase 2 Performance: Caching & optimization 🔜
- Phase 3: Docker demo validation 🔜

## Notes

- All changes will be backward compatible
- No API changes required
- Database migrations not needed
- Django version: 5.1+ support maintained
