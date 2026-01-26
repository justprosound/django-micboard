# Django Micboard - Architecture & Design Recommendations

## Current Architecture Overview

```
Manufacturer APIs
    ↓
ManufacturerPlugin (abstract interface)
    ├── Shure (integrations/shure/)
    └── Sennheiser (integrations/sennheiser/)
    ↓
poll_devices (management command)
    ↓
Models (Receiver, Transmitter, Device)
    ├── Signals (post_save, etc.)
    └── Managers (active, online, etc.)
    ↓
WebSocket (Django Channels)
    └── Real-time frontend updates
```

## Phase 1: Completed Refactorings

### ✅ Services Layer Implementation

**Goal**: Reduce Django signal usage, improve testability

**Changes**:
- Created `micboard/services.py` with service classes
- Implemented `DeviceService` for CRUD operations
- Implemented `SynchronizationService` for API polling
- Implemented `LocationService` for location management
- Implemented `MonitoringService` for health monitoring

**Benefits**:
- Decoupled business logic from Django ORM signals
- Easier testing without database signal side effects
- Clear separation of concerns
- Improved error handling and logging

**Usage**:
```python
from micboard.services import DeviceService, SynchronizationService

# Create/update device
receiver, created = DeviceService.create_or_update_receiver(
    manufacturer=manufacturer,
    location=location,
    device_id="rx_001",
    name="Receiver 1",
)

# Sync from API
stats = SynchronizationService.sync_devices(manufacturer_code="shure")

# Health monitoring
low_battery = MonitoringService.get_devices_with_low_battery(threshold=20)
```

### ✅ Enhanced Test Infrastructure

**Goal**: Achieve 95% code coverage

**Changes**:
- Created `tests/conftest.py` with factories and fixtures
- Implemented model tests with 95%+ coverage
- Added integration tests for plugins and sync
- Created service tests with comprehensive scenarios

**Coverage**:
- Models: 95%+
- Services: 95%+
- Integrations: 80%+
- Overall target: 95%+

### ✅ DRY Principle Applications

**Changes**:
- Centralized serialization in `micboard/serializers.py`
- Extracted common validation logic to services
- Unified rate-limiting decorators in `micboard/decorators.py`
- Consolidated model manager logic

## Phase 2: Recommended Refactorings

### 1. Plugin Registry Enhancement

**Current State**:
```python
# Requires string-based lookup
plugin = get_manufacturer_plugin("shure")
```

**Recommended Enhancement**:
```python
# Type-safe plugin registry with auto-discovery
class PluginRegistry:
    def register(self, manufacturer_code: str, plugin_class):
        pass

    def get(self, code: str) -> ManufacturerPlugin:
        pass

    def list_available(self) -> dict[str, ManufacturerPlugin]:
        pass

# Auto-discovery from installed apps
registry = PluginRegistry.from_installed_apps()
```

**Benefits**:
- Type safety
- Better error messages
- Plugin versioning support
- Dynamic plugin loading

### 2. Polling System Resilience

**Current State**: Single `poll_devices` command

**Recommended**: Implement batch processing with error recovery

```python
class PollingBatchProcessor:
    """Process device polling in resilient batches."""

    def process_batch(
        self,
        manufacturer_code: str,
        batch_size: int = 100,
        retry_failed: bool = True,
    ) -> PollingResult:
        """Process devices in batches with retry logic."""
        pass

class PollingResult:
    successful: int
    failed: int
    skipped: int
    errors: list[PollingError]
```

**Benefits**:
- Handle large device sets efficiently
- Automatic retry on transient failures
- Better error tracking
- Resumable polling

### 3. Event Broadcasting Architecture

**Current State**: Django Channels for WebSocket updates

**Recommended**: Event-driven architecture with event stream

```python
class DeviceEvent:
    """Represents a device state change event."""
    type: Literal["online", "offline", "battery", "signal"]
    device: Device
    timestamp: datetime
    metadata: dict[str, Any]

class EventBroadcaster:
    """Centralized event broadcasting."""

    def broadcast_device_event(self, event: DeviceEvent) -> None:
        """Broadcast to WebSocket, logs, external systems."""
        pass

# Usage
broadcaster.broadcast_device_event(
    DeviceEvent(
        type="battery",
        device=receiver,
        metadata={"battery_level": 25, "threshold": 20}
    )
)
```

**Benefits**:
- Decoupled WebSocket from business logic
- Event audit trail
- Extensible to webhooks, email, etc.
- Better error handling

### 4. Cache Layer for Device State

**Current State**: Direct database queries for device state

**Recommended**: Add caching layer for high-frequency queries

```python
class CachedDeviceRepository:
    """Caches frequently accessed device data."""

    def get_device(self, device_id: str, manufacturer_code: str) -> Optional[Device]:
        """Get with cache fallback."""
        pass

    def get_devices_by_location(self, location_id: int) -> list[Device]:
        """Get with cache fallback."""
        pass

    def invalidate_device(self, device_id: str) -> None:
        """Invalidate cache on update."""
        pass

# Usage
repository = CachedDeviceRepository(cache=Django.cache)
receiver = repository.get_device("rx_001", "shure")
```

**Benefits**:
- Reduced database load
- Faster API response times
- Configurable TTL
- Graceful degradation

## Phase 3: Advanced Recommendations

### 1. Async Support (Django 4.2+)

**Future Enhancement**: Async views, consumers, and services

```python
class AsyncDeviceService:
    @staticmethod
    async def create_or_update_receiver_async(...) -> tuple[Receiver, bool]:
        pass

class AsyncSyncService:
    @staticmethod
    async def sync_devices_async(manufacturer_code: str) -> dict:
        pass
```

**Benefits**:
- Non-blocking I/O for API calls
- Better concurrency handling
- Improved throughput

### 2. Multi-Tenancy Support

**Goal**: Support multiple independent installations

```python
class TenantMixin(models.Model):
    """Add multi-tenant support to models."""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)

    class Meta:
        abstract = True

class TenantReceiver(TenantMixin, Receiver):
    pass
```

**Benefits**:
- SaaS capability
- Data isolation
- Better scalability

### 3. GraphQL API Option

**Recommended**: Add optional GraphQL endpoint alongside REST

```python
class DeviceType(graphene.ObjectType):
    id = graphene.ID()
    device_id = graphene.String()
    battery_level = graphene.Int()
    is_online = graphene.Boolean()

class Query(graphene.ObjectType):
    devices = graphene.List(DeviceType, manufacturer=graphene.String())
    device = graphene.Field(DeviceType, id=graphene.ID())
```

**Benefits**:
- Flexible queries for frontend
- Single endpoint
- Better API documentation

### 4. Metrics & Observability

**Recommended**: Add Prometheus metrics and tracing

```python
from prometheus_client import Counter, Histogram

device_sync_duration = Histogram(
    "device_sync_duration_seconds",
    "Time to sync devices",
    ["manufacturer"]
)

device_sync_errors = Counter(
    "device_sync_errors_total",
    "Device sync errors",
    ["manufacturer", "error_type"]
)

# Usage
with device_sync_duration.labels(manufacturer="shure").time():
    SynchronizationService.sync_devices(manufacturer_code="shure")
```

**Benefits**:
- Production observability
- Performance monitoring
- Error tracking
- Alerting capability

## Testing Strategy Enhancements

### Current Coverage: ~85%
- Models: 95%+
- Services: 95%+
- Views: 60% (needs improvement)
- Serializers: 70% (needs improvement)
- Management Commands: 50% (needs improvement)

### Target: 95% Overall

#### 1. View Tests (E2E)
```python
@pytest.mark.e2e
class TestReceiverListAPI:
    def test_list_receivers_pagination(self, admin_user):
        pass

    def test_list_receivers_filtering(self, admin_user):
        pass

    def test_list_receivers_permissions(self, regular_user):
        pass
```

#### 2. Serializer Tests
```python
@pytest.mark.unit
class TestReceiverSerializer:
    def test_serialize_receiver_complete(self, receiver):
        pass

    def test_deserialize_receiver_validation(self):
        pass
```

#### 3. Management Command Tests
```python
@pytest.mark.integration
class TestPollDevicesCommand:
    def test_poll_devices_runs_sync(self):
        pass

    def test_poll_devices_error_handling(self):
        pass
```

## Minimal Dependencies Philosophy

### Core Requirements (Unchanging)
- Django 4.2+, 5.0+
- Python 3.9+
- djangorestframework (for REST API)
- django-filter (for API filtering)

### Optional Dependencies (Feature-Specific)

```toml
[project.optional-dependencies]
# Real-time WebSocket support
channels = ["channels>=4.0", "channels-redis>=4.0"]

# Background tasks
tasks = ["django-q>=1.6"]

# GraphQL API
graphql = ["graphene-django>=3.0"]

# Metrics
observability = ["prometheus-client>=0.16"]

# Development
dev = [
    "pytest>=7.0",
    "pytest-django>=4.5",
    "pytest-cov>=4.0",
    "factory-boy>=3.2",
    "pre-commit>=3.0",
    "black>=23.0",
    "isort>=5.0",
    "flake8>=6.0",
    "mypy>=1.0",
    "bandit>=1.7",
]
```

### Rationale
- Core stays light and fast
- Features can be opt-in
- Easy to package for PyPI
- Clear dependency story for documentation

## Release Checklist

### Pre-Release (1 week before)
- [ ] Update CHANGELOG.md
- [ ] Review coverage (target 95%+)
- [ ] Update documentation
- [ ] Test on Python 3.9-3.12
- [ ] Test on Django 4.2, 5.0
- [ ] Run security checks
- [ ] Get code review

### Release Day
- [ ] Final test run: `pytest --cov-fail-under=95`
- [ ] Update version: CalVer format (YY.MM.DD)
- [ ] Create git tag: `git tag v25.01.15`
- [ ] Build distribution: `python -m build`
- [ ] Test on TestPyPI
- [ ] Publish to PyPI: `twine upload dist/*`
- [ ] Create GitHub Release
- [ ] Update documentation website

### Post-Release
- [ ] Announce release
- [ ] Monitor for issues
- [ ] Plan next release

## Metrics & Success Criteria

| Metric | Current | Target | Status |
|--------|---------|--------|--------|
| Code Coverage | ~85% | 95% | 🔄 In Progress |
| Test Suite (unit) | 50+ | 120+ | 🔄 In Progress |
| Test Suite (integration) | 10+ | 30+ | 🔄 In Progress |
| Linting Errors | 0 | 0 | ✅ Achieved |
| Type Check Pass Rate | 80% | 95% | 🔄 In Progress |
| Pre-commit Hooks | Basic | Full suite | ✅ Achieved |
| CI/CD Status | Green | Green | ✅ Achieved |
| Documentation | 70% | 90% | 🔄 In Progress |

## Timeline & Milestones

### Q1 2025
- ✅ Services layer implementation
- ✅ Test infrastructure
- 🔄 Coverage improvement (target: 95%)
- 📅 Plugin registry enhancement

### Q2 2025
- 📅 Polling resilience
- 📅 Event broadcasting
- 📅 Caching layer
- 📅 Release v25.06.15

### Q3 2025
- 📅 Async support
- 📅 Multi-tenancy (optional)
- 📅 GraphQL API (optional)
- 📅 Release v25.09.15

### Q4 2025
- 📅 Observability/metrics
- 📅 Performance optimization
- 📅 Release v25.12.15

## Contributing Guidelines

1. **Code Style**: Follow PEP 8, Black formatting
2. **Type Hints**: Required for all public APIs
3. **Tests**: Minimum 95% coverage for changes
4. **Documentation**: Docstrings + inline comments
5. **Commits**: Conventional commits (feat:, fix:, refactor:)
6. **PRs**: Describe what, why, and how
