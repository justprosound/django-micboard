
# Phase 2: Service Layer Integration - Implementation Guide

## Overview

Phase 1 delivered a complete, production-ready service layer. Phase 2 focuses on integrating these services into existing code and building new features on top of them.

This document provides concrete guidance for Phase 2 integration.

## Phase 2 Deliverables

### Primary Tasks

1. **Refactor Management Commands** (Week 1-2)
   - Update `poll_devices.py` to use services
   - Create new management commands for monitoring
   - Add health check commands

2. **Refactor REST API Views** (Week 3-4)
   - Update existing views to use services
   - Add error handling
   - Implement pagination

3. **Add Comprehensive Tests** (Week 5-6)
   - Unit tests for all service methods
   - Integration tests for views/commands
   - Mock external API calls

4. **Documentation & Training** (Week 7-8)
   - Document team patterns
   - Create training materials
   - Update developer onboarding

## Files Added for Phase 2 Support

### 1. `micboard/signals.py` (NEW)
**Purpose**: Django signal handlers for audit logging and cross-app notifications

**Key Points**:
- Keeps signals minimal and focused on side effects
- Demonstrates proper signal patterns
- Logs important events for audit trail
- Ready to use - just connect in `apps.py`

**Usage**:
- Automatically triggered when models are saved/deleted
- No manual registration needed (handled by `apps.py`)
- Provides audit trail for compliance

### 2. `micboard/apps.py` (NEW)
**Purpose**: Django app configuration with signal registration

**Key Points**:
- Registers signals when app is ready
- Properly imports signals module
- Follows Django best practices

**Integration**:
- Already functional - signals are active
- Can be extended for future features

### 3. `micboard/management_command_template.py` (NEW)
**Purpose**: Reference implementation for management command refactoring

**What It Shows**:
- How to use `ManufacturerService.sync_devices_for_manufacturer()`
- How to use `ConnectionHealthService` for health monitoring
- How to use `DeviceService` for statistics
- Proper command structure and error handling
- Rate-limit awareness

**How to Use in Phase 2**:
```bash
1. Review the template
2. Update poll_devices.py using this pattern
3. Test locally
4. Deploy to development
5. Monitor for issues
```

### 4. `micboard/views_template.py` (NEW)
**Purpose**: Reference implementation for REST API view refactoring

**What It Shows**:
- How to use services in APIView classes
- Error handling patterns
- Using rate limit decorators
- Proper serialization
- Search/filter patterns
- Status code usage

**Classes Demonstrated**:
- `DeviceListView` - Query with search
- `DeviceStatusView` - Update operations
- `AssignmentListView` - Assignment management
- `LocationListView` - Location management
- `device_stats_view` - Function-based view

**How to Use in Phase 2**:
```python
# Copy patterns from template
# Don't copy code verbatim - adapt to your views

# Before:
def device_list(request):
    devices = Receiver.objects.filter(active=True)
    return Response(...)

# After (using template pattern):
def device_list(request):
    devices = DeviceService.get_active_receivers()
    return Response(...)
```

### 5. `micboard/test_utils.py` (NEW)
**Purpose**: Testing utilities for service layer tests

**Base Classes**:
- `ServiceTestCase` - Base with common fixtures
- `DeviceServiceTestCase` - For device service tests
- `AssignmentServiceTestCase` - For assignment tests
- `LocationServiceTestCase` - For location tests
- `ManufacturerServiceTestCase` - For manufacturer tests

**Helper Functions**:
- `create_test_user()` - Create test user
- `create_test_receiver()` - Create test receiver
- `create_test_transmitter()` - Create test transmitter
- `create_test_location()` - Create test location
- `create_test_assignment()` - Create test assignment

**How to Use in Phase 2**:
```python
from micboard.test_utils import ServiceTestCase, create_test_receiver

class TestDeviceService(ServiceTestCase):
    def test_sync_status(self):
        receiver = create_test_receiver(online=True)
        DeviceService.sync_device_status(device_obj=receiver, online=False)

        receiver.refresh_from_db()
        self.assertFalse(receiver.online)
```

## Phase 2 Integration Workflow

### Step 1: Review Templates
```bash
1. Read micboard/management_command_template.py
2. Read micboard/views_template.py
3. Read micboard/test_utils.py
4. Understand patterns
```

### Step 2: Refactor Management Commands
```bash
1. Open micboard/management/commands/poll_devices.py
2. Compare with template
3. Replace direct model access with service calls
4. Update error handling
5. Test locally
6. Commit changes
```

### Step 3: Refactor Views
```bash
1. Identify high-priority views
2. Use views_template.py as reference
3. Replace direct model access with services
4. Add rate limiting if needed
5. Update error handling
6. Write integration tests
7. Commit changes
```

### Step 4: Add Tests
```bash
1. Use test_utils.py base classes
2. Write unit tests for services (not needed - already tested)
3. Write integration tests for views
4. Write integration tests for commands
5. Achieve 80%+ coverage
6. All tests passing
```

### Step 5: Deploy
```bash
1. All tests passing locally
2. Code review approved
3. Merge to development
4. Test in development environment
5. Monitor for issues
6. Deploy to staging
7. Final testing
8. Deploy to production
9. Monitor metrics
```

## Phase 2 Checklist

### Week 1: Review & Planning
- [ ] All developers read Phase 1 documentation
- [ ] Team reviews service API design
- [ ] Identify high-priority areas to refactor
- [ ] Create refactoring schedule
- [ ] Assign tasks to developers

### Week 2-3: Management Commands
- [ ] Review management_command_template.py
- [ ] Refactor poll_devices.py
- [ ] Test with mock data
- [ ] Test with real Shure/Sennheiser APIs (if available)
- [ ] Document any issues
- [ ] Code review and merge

### Week 4-5: REST API Views
- [ ] Review views_template.py
- [ ] Identify priority views
- [ ] Refactor high-priority views
- [ ] Add error handling
- [ ] Write integration tests
- [ ] Code review and merge

### Week 6-7: Testing & Documentation
- [ ] Write unit tests for service methods (optional)
- [ ] Write integration tests for views
- [ ] Write integration tests for commands
- [ ] Achieve 80%+ code coverage
- [ ] Document team patterns
- [ ] Create training materials

### Week 8+: Continuous Integration
- [ ] Deploy to production
- [ ] Monitor performance
- [ ] Monitor error rates
- [ ] Gather team feedback
- [ ] Plan Phase 3 features
- [ ] Identify optimization opportunities

## Common Integration Issues & Solutions

### Issue 1: Circular Imports

**Problem**: Services import models, views import services, models import views

**Solution**:
```python
# Use TYPE_CHECKING guards
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from micboard.models import Receiver

@staticmethod
def sync_status(device_obj: Receiver) -> None:
    pass
```

### Issue 2: Performance Regression

**Problem**: Service methods causing N+1 queries

**Solution**:
```python
# Use select_related and prefetch_related
devices = DeviceService.get_active_receivers()
    .select_related('location')
    .prefetch_related('assignments')
```

### Issue 3: Missing Exception Handling

**Problem**: Forgot to catch service exceptions in view

**Solution**:
```python
try:
    assignment = AssignmentService.create_assignment(...)
except AssignmentAlreadyExistsError as e:
    return Response({'error': str(e)}, status=400)
except ValueError as e:
    return Response({'error': str(e)}, status=400)
```

### Issue 4: Breaking API Changes

**Problem**: Service API doesn't match view expectations

**Solution**:
- Always use keyword-only parameters
- Document exceptions clearly
- Test with real view code before deploying
- Use type hints for IDE support

## Testing Strategy for Phase 2

### Unit Tests (for services)
- Optional - services already have clear contracts
- If added, should test edge cases
- Mock external dependencies

### Integration Tests (for views)
- Required - test end-to-end flows
- Use test_utils.py for fixtures
- Mock external APIs
- Test error cases

### Integration Tests (for commands)
- Required - test command execution
- Use test_utils.py for fixtures
- Mock external APIs
- Test command-line arguments

### Example Test Structure

```python
from django.test import TestCase
from micboard.test_utils import ServiceTestCase
from micboard.services import AssignmentService

class TestAssignmentIntegration(ServiceTestCase):
    def test_create_assignment_view(self):
        """Test assignment creation through REST API."""
        from django.test import Client
        from micboard.models import Assignment

        client = Client()

        response = client.post(
            '/api/assignments/',
            {
                'device_id': self.receiver1.id,
                'alert_enabled': True
            }
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Assignment.objects.filter(
                user=self.user,
                device_id=self.receiver1.id
            ).exists()
        )
```

## Performance Optimization Points

### Database Queries
- Use `select_related()` for foreign keys
- Use `prefetch_related()` for many-to-many
- Consider caching for frequently accessed data

### API Calls
- Batch manufacturer API calls
- Implement exponential backoff for retries
- Cache API responses where appropriate

### Signal Handlers
- Keep signals minimal
- Don't do expensive operations in signals
- Use task queue for async operations

## Monitoring & Metrics

### What to Track During Phase 2

1. **Performance**
   - Average response time
   - Database query count
   - API call count
   - Memory usage

2. **Reliability**
   - Error rate
   - Exception types
   - Service availability
   - Connection health

3. **Adoption**
   - % of views using services
   - % of commands using services
   - Code review turnaround
   - Team feedback

### How to Measure

```python
# Add to monitoring dashboard
from django.core.cache import cache
from micboard.services import ConnectionHealthService, DeviceService

def collect_metrics():
    stats = {
        'active_connections': ConnectionHealthService.get_connection_stats()['active_connections'],
        'online_devices': DeviceService.count_online_devices(),
        'timestamp': now(),
    }
    cache.set('micboard_metrics', stats, 3600)
    return stats
```

## Phase 2 Success Criteria

### Code Quality
- [ ] 100% of new code uses services
- [ ] 80%+ of existing code refactored to use services
- [ ] 100% of views have rate limiting
- [ ] 100% error cases handled
- [ ] All tests passing

### Performance
- [ ] No response time regression
- [ ] Database queries optimized
- [ ] API calls batched where possible
- [ ] Memory usage stable

### Documentation
- [ ] All views documented
- [ ] All commands documented
- [ ] Team patterns documented
- [ ] Troubleshooting guide created

### User Satisfaction
- [ ] Team finds services easy to use
- [ ] Quick reference card sufficient
- [ ] No major pain points identified
- [ ] Feedback positive

## Next Phase Planning (Phase 3)

Once Phase 2 is complete, consider:

1. **Async/Task Queue Integration**
   - Use Django-Q for background jobs
   - Offload slow operations

2. **Event-Driven Architecture**
   - Services emit events
   - Other services/systems subscribe

3. **Performance Optimization**
   - Caching layer
   - Query optimization
   - API batching

4. **Advanced Features**
   - Bulk operations
   - Webhook support
   - Real-time sync

## Support & Questions During Phase 2

### Quick Reference
- [docs/services-quick-reference.md](../docs/services-quick-reference.md) - Method lookup
- [docs/services-best-practices.md](../docs/services-best-practices.md) - Patterns
- [docs/services-implementation-patterns.md](../docs/services-implementation-patterns.md) - Examples

### Communication Channels
- **Slack**: #micboard-dev
- **Issues**: GitHub Issues with `phase2` label
- **Docs**: Update as you learn

### Escalation Path
1. Check docs
2. Ask in Slack
3. Code review
4. Team discussion
5. Architecture review

## Conclusion

Phase 2 transforms Phase 1's service layer foundation into a production system. By following this guide, your team will:

- ✅ Maintain code quality
- ✅ Avoid common pitfalls
- ✅ Achieve goals on schedule
- ✅ Build team expertise
- ✅ Set up for Phase 3 success

**Start with the templates, follow the checklist, and reference the docs as needed.**

Good luck with Phase 2! 🚀
