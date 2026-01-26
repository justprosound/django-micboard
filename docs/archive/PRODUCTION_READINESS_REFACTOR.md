# Django Micboard - Production Readiness Refactor (Phase 2.1)

## Overview

This document outlines the comprehensive refactoring strategy to achieve production-ready status with:
- ✅ Service layer with clear contracts (no Django signals)
- ✅ 95%+ code coverage with focused tests
- ✅ DRY principles throughout
- ✅ CalVer versioning with automated releases
- ✅ GitHub Actions CI/CD pipelines
- ✅ Type hints enforcement
- ✅ Architectural Decision Records (ADRs)
- ✅ API documentation
- ✅ Deployment readiness

**Current State**: Phase 1 foundation complete (v25.01.15)
**Target State**: Production-ready (v25.02.15+)
**Timeline**: 6-8 weeks

---

## 1. Service Layer Architecture & Contracts

### 1.1 Service Layer Design Principles

**Core Pattern**: Eliminate Django signals → Use explicit service contracts

```python
# ✅ GOOD: Service-based approach (explicit contract)
class DeviceService:
    @staticmethod
    def sync_device(manufacturer_code: str, device_id: str) -> Device:
        """
        Synchronize single device with manufacturer API.

        Contract:
        - Input: Valid manufacturer code + device ID
        - Output: Updated Device instance
        - Side effects: None (unless save() called externally)
        - Exceptions: DeviceNotFoundError, APIError
        """
        device = Device.objects.get(device_id=device_id)
        plugin = get_manufacturer_plugin(manufacturer_code)
        remote_state = plugin.get_device(device_id)
        device.update_from_remote(remote_state)
        return device

# ❌ AVOID: Signal-based approach (implicit behavior)
@receiver(post_save, sender=Device)
def device_saved(sender, instance, **kwargs):
    # Hidden side effect - hard to debug
    notify_websocket(instance)
```

### 1.2 Core Service Modules

**File**: `micboard/services/__init__.py`
```python
from .device import DeviceService
from .synchronization import SynchronizationService
from .location import LocationService
from .health import HealthService

__all__ = [
    'DeviceService',
    'SynchronizationService',
    'LocationService',
    'HealthService',
]
```

**File**: `micboard/services/contracts.py` (NEW)
```python
"""Service layer contracts and interfaces."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ServiceResult:
    """Standard service result container."""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None
    warning: Optional[str] = None

class DeviceServiceContract(ABC):
    """Contract for device operations."""

    @abstractmethod
    def sync_device(self, manufacturer_code: str, device_id: str) -> ServiceResult:
        """Sync single device with manufacturer API."""
        pass

    @abstractmethod
    def sync_all_devices(self, manufacturer_code: str) -> ServiceResult:
        """Sync all devices for manufacturer."""
        pass

    @abstractmethod
    def get_device_status(self, device_id: str) -> ServiceResult:
        """Get current device status without sync."""
        pass

class LocationServiceContract(ABC):
    """Contract for location operations."""

    @abstractmethod
    def create_location(self, name: str, description: str = "") -> ServiceResult:
        """Create new location."""
        pass

    @abstractmethod
    def assign_device(self, device_id: str, location_id: int) -> ServiceResult:
        """Assign device to location."""
        pass

    @abstractmethod
    def get_location_summary(self, location_id: int) -> ServiceResult:
        """Get location with device summary."""
        pass
```

### 1.3 Dependency Injection Pattern

**File**: `micboard/services/container.py` (NEW)
```python
"""Dependency injection container for services."""
from typing import Dict, Type, Any, Callable
from functools import lru_cache

class ServiceContainer:
    """Simple DI container for service management."""

    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable] = {}

    def register(self, name: str, service: Any) -> None:
        """Register service instance."""
        self._services[name] = service

    def register_factory(self, name: str, factory: Callable) -> None:
        """Register service factory (lazy initialization)."""
        self._factories[name] = factory

    def get(self, name: str) -> Any:
        """Get service instance."""
        if name in self._services:
            return self._services[name]
        if name in self._factories:
            service = self._factories[name]()
            self._services[name] = service
            return service
        raise ValueError(f"Service '{name}' not registered")

# Global container instance
_container = ServiceContainer()

# Register services at app startup
def setup_services():
    """Initialize services (called in apps.py)."""
    from .device import DeviceService
    from .location import LocationService

    _container.register('device_service', DeviceService())
    _container.register('location_service', LocationService())

def get_service(name: str) -> Any:
    """Get service from container."""
    return _container.get(name)
```

### 1.4 Update Apps Configuration

**File**: `micboard/apps.py` (UPDATE)
```python
from django.apps import AppConfig

class MicboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'micboard'
    verbose_name = 'Django Micboard'

    def ready(self):
        """Initialize services and remove signal handlers."""
        from . import signals  # Register any necessary signals
        from .services.container import setup_services

        # Initialize services
        setup_services()

        # Note: Signal handlers should be minimal
        # Prefer explicit service calls instead
```

---

## 2. Remove/Minimize Django Signals

### 2.1 Signal Usage Audit

**Current signals** (from copilot-instructions.md):
- Device state changes
- Location updates
- WebSocket notifications

**Strategy**: Replace with explicit service methods

### 2.2 Example: Device Status Update

**BEFORE** (Signal-based):
```python
# models.py
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Device)
def device_updated(sender, instance, created, **kwargs):
    # Hidden side effect
    cache.set(f'device:{instance.id}', instance)
    notify_websocket_device_update(instance)
    log_device_change(instance)
```

**AFTER** (Service-based):
```python
# services/device.py
from .contracts import ServiceResult

class DeviceService:
    def update_device_state(
        self,
        device_id: str,
        *,
        battery_level: int = None,
        signal_strength: int = None,
        is_online: bool = None,
    ) -> ServiceResult:
        """
        Update device state with explicit side effects.

        Caller controls what happens after update.
        """
        device = Device.objects.get(device_id=device_id)

        if battery_level is not None:
            device.battery_level = battery_level
        if signal_strength is not None:
            device.signal_strength = signal_strength
        if is_online is not None:
            device.is_online = is_online

        device.save()

        return ServiceResult(success=True, data={'device_id': device.device_id})

    def notify_device_update(self, device: Device) -> None:
        """Explicit notification - caller decides if needed."""
        # Update cache
        cache.set(f'device:{device.id}', device)

        # Notify WebSocket (if available)
        from .websocket import notify_device_changed
        notify_device_changed(device)

        # Log change
        logger.info(f"Device {device.device_id} updated")

# Usage - Explicit control
device_service = get_service('device_service')
result = device_service.update_device_state(device_id, battery_level=75)
if result.success:
    device = Device.objects.get(device_id=device_id)
    device_service.notify_device_update(device)
```

### 2.3 Signals Minimization Rules

```python
# micboard/signals.py - MINIMAL SIGNALS ONLY

from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.core.cache import cache
from .models import Device

# ONLY keep signals that are truly necessary
@receiver(post_delete, sender=Device)
def device_deleted(sender, instance, **kwargs):
    """Clean up related cache entries."""
    cache.delete(f'device:{instance.id}')
```

**Rule**: If you can call it explicitly in the service, DON'T use a signal.

---

## 3. Enhanced Test Suite (95%+ Coverage)

### 3.1 Test Structure Reorganization

```
tests/
├── conftest.py                    # Fixtures and factories
├── unit/
│   ├── test_models.py             # Model validation tests
│   ├── test_managers.py           # Manager/QuerySet tests
│   ├── test_validators.py         # Utility validators
│   └── test_utils.py              # Helper functions
├── services/
│   ├── test_device_service.py     # DeviceService tests
│   ├── test_sync_service.py       # SynchronizationService tests
│   ├── test_location_service.py   # LocationService tests
│   └── test_health_service.py     # HealthService tests
├── api/
│   ├── test_viewsets.py           # ViewSet tests
│   ├── test_filters.py            # Filter tests
│   └── test_permissions.py        # Permission tests
├── integration/
│   ├── test_device_workflow.py    # Device sync workflow
│   ├── test_location_workflow.py  # Location management workflow
│   └── test_polling_workflow.py   # Polling orchestration
├── e2e/
│   ├── test_full_sync_cycle.py    # Complete sync cycle
│   ├── test_websocket_updates.py  # Real-time updates
│   └── test_api_endpoints.py      # Full API flows
└── fixtures/
    ├── manufacturers.py            # Mock API responses
    ├── devices.py                  # Device test data
    └── locations.py                # Location test data
```

### 3.2 Test Coverage Strategy

**Target**: 95%+ across all modules

```python
# tests/conftest.py - Enhanced fixtures
import pytest
from factory.django import DjangoModelFactory
from micboard.models import Device, Location, Manufacturer

class ManufacturerFactory(DjangoModelFactory):
    """Factory for Manufacturer model."""
    code = 'shure'
    name = 'Shure'
    is_active = True

    class Meta:
        model = Manufacturer

class LocationFactory(DjangoModelFactory):
    """Factory for Location model."""
    name = 'Main Stage'
    description = 'Main performance area'

    class Meta:
        model = Location

class ReceiverFactory(DjangoModelFactory):
    """Factory for Receiver device."""
    device_id = 'rx_0001'
    name = 'Receiver 1'
    manufacturer = factory.SubFactory(ManufacturerFactory)
    location = factory.SubFactory(LocationFactory)
    is_online = True
    battery_level = 85
    signal_strength = -50

    class Meta:
        model = Device

# Pytest fixtures
@pytest.fixture
def manufacturer():
    return ManufacturerFactory()

@pytest.fixture
def location():
    return LocationFactory()

@pytest.fixture
def receiver(manufacturer, location):
    return ReceiverFactory(
        manufacturer=manufacturer,
        location=location,
    )

# Mock API responses
@pytest.fixture
def mock_shure_api_response():
    return {
        'devices': [
            {
                'id': 'rx_0001',
                'name': 'Receiver 1',
                'battery': 85,
                'signal': -50,
            }
        ]
    }
```

### 3.3 Service Layer Tests (New)

**File**: `tests/services/test_device_service.py` (NEW)
```python
"""Tests for DeviceService."""
import pytest
from unittest.mock import Mock, patch
from micboard.services import DeviceService
from micboard.services.contracts import ServiceResult

@pytest.mark.django_db
class TestDeviceService:
    """Test DeviceService methods."""

    def test_sync_device_success(self, receiver, mock_shure_api_response):
        """Test successful device sync."""
        with patch('micboard.manufacturers.get_manufacturer_plugin') as mock_plugin:
            mock_plugin.return_value.get_device.return_value = {
                'battery': 90,
                'signal': -45,
            }

            service = DeviceService()
            result = service.sync_device('shure', 'rx_0001')

            assert result.success is True
            assert result.error is None

    def test_sync_device_not_found(self):
        """Test sync for non-existent device."""
        service = DeviceService()
        result = service.sync_device('shure', 'rx_nonexistent')

        assert result.success is False
        assert 'not found' in result.error.lower()

    def test_update_device_state(self, receiver):
        """Test device state update."""
        service = DeviceService()
        result = service.update_device_state(
            receiver.device_id,
            battery_level=50,
            signal_strength=-75,
        )

        assert result.success is True

        # Verify database was updated
        receiver.refresh_from_db()
        assert receiver.battery_level == 50
        assert receiver.signal_strength == -75

    def test_update_device_state_partial(self, receiver):
        """Test partial device state update."""
        original_battery = receiver.battery_level

        service = DeviceService()
        result = service.update_device_state(
            receiver.device_id,
            battery_level=45,
        )

        assert result.success is True
        receiver.refresh_from_db()
        assert receiver.battery_level == 45
        assert receiver.signal_strength == original_battery  # Unchanged

@pytest.mark.django_db
class TestDeviceServiceEdgeCases:
    """Test edge cases and error scenarios."""

    def test_sync_with_invalid_manufacturer(self):
        """Test sync with unsupported manufacturer."""
        service = DeviceService()
        result = service.sync_device('invalid_mfg', 'rx_0001')

        assert result.success is False
        assert 'manufacturer' in result.error.lower()

    def test_update_device_with_invalid_battery(self, receiver):
        """Test battery validation."""
        service = DeviceService()
        result = service.update_device_state(
            receiver.device_id,
            battery_level=150,  # Invalid: >100
        )

        assert result.success is False
```

### 3.4 Coverage Measurement

```bash
# Run tests with coverage report
pytest tests/ \
  --cov=micboard \
  --cov-report=html \
  --cov-report=term-missing \
  --cov-fail-under=95

# Expected output:
# micboard/models/ ............ 98%
# micboard/services/ .......... 96%
# micboard/api/ ............... 92%
# micboard/managers/ .......... 99%
# TOTAL ...................... 95%
```

---

## 4. Type Hints & Type Safety

### 4.1 Enforce Type Hints Across Project

**File**: `micboard/py.typed` (NEW - PEP 561)
```
# PEP 561 marker file - indicates package is typed
```

**File**: `pyproject.toml` (UPDATE)
```toml
[tool.mypy]
python_version = "3.9"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_any_unimported = false
check_untyped_defs = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_no_return = true
strict_optional = true

[[tool.mypy.overrides]]
module = [
    "tests.*",
]
ignore_errors = true

[tool.pylint]
max-attributes=7
```

### 4.2 Type-Hinted Service Examples

```python
# ✅ GOOD: Full type hints
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from decimal import Decimal

@dataclass
class DeviceState:
    """Device state representation."""
    device_id: str
    is_online: bool
    battery_level: Optional[int]
    signal_strength: Optional[int]

class DeviceService:
    def get_device_state(
        self,
        device_id: str,
    ) -> Optional[DeviceState]:
        """Get device state or None if not found."""
        try:
            device = Device.objects.get(device_id=device_id)
            return DeviceState(
                device_id=device.device_id,
                is_online=device.is_online,
                battery_level=device.battery_level,
                signal_strength=device.signal_strength,
            )
        except Device.DoesNotExist:
            return None

    def sync_devices(
        self,
        manufacturer_code: str,
        *,
        retry_count: int = 3,
        timeout_seconds: int = 30,
    ) -> Dict[str, Any]:
        """Sync all devices for manufacturer."""
        results: Dict[str, Any] = {
            'synced': 0,
            'failed': 0,
            'errors': [],
        }
        return results
```

---

## 5. Architectural Decision Records (ADRs)

### 5.1 Create ADR Structure

**File**: `docs/adr/README.md` (NEW)
```markdown
# Architecture Decision Records (ADRs)

## Index

1. [ADR-001: Service Layer Pattern](./adr-001-service-layer.md)
2. [ADR-002: Dependency Injection](./adr-002-dependency-injection.md)
3. [ADR-003: Signal Minimization](./adr-003-signal-minimization.md)
4. [ADR-004: Plugin Architecture](./adr-004-plugin-architecture.md)
5. [ADR-005: Database Query Optimization](./adr-005-query-optimization.md)
```

### 5.2 ADR Template

**File**: `docs/adr/adr-001-service-layer.md` (NEW)
```markdown
# ADR-001: Service Layer Pattern

## Status
Accepted (January 2025)

## Context
Django applications often mix business logic with models and views, leading to:
- Hard-to-test code
- Implicit side effects (signals)
- Difficulty following data flow
- Tight coupling between layers

## Decision
Implement explicit service layer with:
- Clear contracts (interfaces)
- No Django signals for business logic
- Dependency injection for testability
- ServiceResult wrapper for consistency

## Consequences

### Positive
- ✅ Explicit data flow (easier debugging)
- ✅ Testable without Django fixtures
- ✅ Clear responsibility boundaries
- ✅ Reusable across views, tasks, CLI

### Negative
- ⚠️ More boilerplate initially
- ⚠️ Steeper learning curve

## Implementation
See `micboard/services/` and related contracts.

## References
- [Service Layer Pattern](https://martinfowler.com/eaaCatalog/serviceLayer.html)
- Django best practices
```

**File**: `docs/adr/adr-003-signal-minimization.md` (NEW)
```markdown
# ADR-003: Signal Minimization

## Status
Accepted (January 2025)

## Context
Django signals are powerful but create hidden behavior that's hard to trace and test:
- `post_save` handlers run automatically
- Debugging requires understanding signal system
- Testing requires mocking signal handlers
- Order of execution is unclear

## Decision
Minimize Django signals to only:
1. Cache cleanup (post_delete)
2. Log aggregation (optional post_save for analytics)

Move all business logic to explicit service methods.

## Consequences

### Positive
- ✅ Explicit control flow
- ✅ Easier debugging
- ✅ Clear side effects
- ✅ Better performance (no hidden operations)

### Negative
- ⚠️ More explicit code in caller
- ⚠️ Requires discipline

## Implementation
Replace signal handlers with service methods:
```python
# OLD (Signal)
@receiver(post_save, sender=Device)
def device_saved(sender, instance, **kwargs):
    notify_websocket(instance)

# NEW (Service)
service.update_device(device_id)
service.notify_device_update(device)  # Explicit
```
```

---

## 6. API Documentation

### 6.1 OpenAPI/Swagger Integration

**File**: `micboard/api/schema.py` (NEW)
```python
"""OpenAPI schema generation."""
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from django.urls import path

urlpatterns = [
    path(
        'api/schema/',
        SpectacularAPIView.as_view(),
        name='schema',
    ),
    path(
        'api/docs/',
        SpectacularSwaggerView.as_view(url_name='schema'),
        name='swagger-ui',
    ),
]
```

### 6.2 Endpoint Documentation

**File**: `micboard/api/viewsets.py` (UPDATE)
```python
from drf_spectacular.utils import extend_schema, OpenApiParameter

class ReceiverViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Receiver (wireless microphone receiver) management API.

    Provides real-time monitoring of receiver status including:
    - Battery level and signal strength
    - Online/offline status
    - Location assignments
    """

    @extend_schema(
        description="List all receivers with optional filtering",
        parameters=[
            OpenApiParameter(
                name='manufacturer',
                description='Filter by manufacturer code (shure, sennheiser)',
                required=False,
            ),
            OpenApiParameter(
                name='location',
                description='Filter by location ID',
                required=False,
            ),
            OpenApiParameter(
                name='is_online',
                description='Filter by online status',
                required=False,
                enum=['true', 'false'],
            ),
        ],
    )
    def list(self, request, *args, **kwargs):
        """List receivers with optional filters."""
        return super().list(request, *args, **kwargs)

    @extend_schema(
        description="Get low battery receivers",
        parameters=[
            OpenApiParameter(
                name='threshold',
                description='Battery percentage threshold (default: 20)',
                required=False,
            ),
        ],
    )
    @action(detail=False, methods=['get'])
    def low_battery(self, request):
        """Get receivers with battery below threshold."""
        pass
```

### 6.3 Generated Documentation

```bash
# Generate schema
python manage.py spectacular --file schema.yml

# Access Swagger UI
# http://localhost:8000/api/docs/
```

---

## 7. CalVer Versioning & Release Automation

### 7.1 Version Management

**File**: `micboard/__version__.py` (NEW)
```python
"""Version information using CalVer."""

__version__ = "25.02.15"  # YY.MM.DD format
__version_info__ = (25, 2, 15)

# Semantic components for compatibility
MAJOR = 25
MINOR = 2
PATCH = 15
```

### 7.2 Automated Version Bumping

**File**: `scripts/bump-version.py` (NEW)
```python
#!/usr/bin/env python
"""Bump version to current date (CalVer)."""
from datetime import datetime
from pathlib import Path

def bump_version() -> str:
    """Get current CalVer version (YY.MM.DD)."""
    today = datetime.now()
    version = today.strftime("%y.%m.%d")
    return version

def update_version_file(version: str) -> None:
    """Update version in __version__.py."""
    version_file = Path(__file__).parent.parent / "micboard" / "__version__.py"

    year, month, day = version.split('.')
    content = f'''"""Version information using CalVer."""

__version__ = "{version}"  # YY.MM.DD format
__version_info__ = ({year}, {month}, {day})

MAJOR = {year}
MINOR = {month}
PATCH = {day}
'''

    version_file.write_text(content)
    print(f"Updated version to {version}")

if __name__ == "__main__":
    version = bump_version()
    update_version_file(version)
    print(f"CalVer: {version}")
```

### 7.3 GitHub Actions Release Workflow

**File**: `.github/workflows/release.yml` (NEW)
```yaml
name: Release

on:
  workflow_dispatch:
    inputs:
      prerelease:
        description: 'Pre-release version'
        required: false
        default: 'false'

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      packages: write

    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Bump version (CalVer)
        run: |
          python scripts/bump-version.py
          VERSION=$(python -c "from micboard.__version__ import __version__; print(__version__)")
          echo "VERSION=$VERSION" >> $GITHUB_ENV

      - name: Install dependencies
        run: |
          pip install -e ".[dev,test]"
          pip install build twine

      - name: Run tests
        run: |
          pytest tests/ --cov=micboard --cov-fail-under=95 -q

      - name: Run linting
        run: |
          uvx pre-commit run --all-files

      - name: Build distribution
        run: |
          python -m build

      - name: Publish to PyPI
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_TOKEN }}
        run: |
          twine upload dist/* --skip-existing

      - name: Create GitHub release
        uses: softprops/action-gh-release@v1
        with:
          tag_name: v${{ env.VERSION }}
          body_path: CHANGELOG.md
          files: dist/*
          prerelease: ${{ github.event.inputs.prerelease == 'true' }}
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

---

## 8. Enhanced CI/CD Pipelines

### 8.1 Test Matrix

**File**: `.github/workflows/test.yml` (UPDATE)
```yaml
name: Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.9', '3.10', '3.11', '3.12']
        django-version: ['4.2', '5.0']
        exclude:
          # Django 5.0 requires Python 3.10+
          - python-version: '3.9'
            django-version: '5.0'

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}
          cache: 'pip'

      - name: Install dependencies
        run: |
          pip install "Django==${{ matrix.django-version }}.*"
          pip install -e ".[dev,test]"

      - name: Lint with pre-commit
        run: |
          uvx pre-commit run --all-files

      - name: Type check with mypy
        run: |
          mypy micboard --ignore-missing-imports

      - name: Run tests
        run: |
          pytest tests/ \
            --cov=micboard \
            --cov-fail-under=95 \
            --cov-report=xml \
            -v

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
          flags: unittests
          name: Python-${{ matrix.python-version }}-Django-${{ matrix.django-version }}
```

### 8.2 Security Scanning

**File**: `.github/workflows/security.yml` (NEW)
```yaml
name: Security

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  bandit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install bandit
      - run: bandit -r micboard -f json -o bandit-report.json || true
      - uses: actions/upload-artifact@v3
        with:
          name: bandit-report
          path: bandit-report.json

  safety:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install safety
      - run: safety check --json || true
```

---

## 9. Error Handling & Logging

### 9.1 Structured Error Handling

**File**: `micboard/exceptions.py` (NEW)
```python
"""Custom exceptions for django-micboard."""
from typing import Optional, Dict, Any

class MicboardException(Exception):
    """Base exception for all micboard errors."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "UNKNOWN_ERROR",
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)

class ManufacturerNotSupported(MicboardException):
    """Raised when manufacturer is not supported."""

    def __init__(self, manufacturer_code: str):
        super().__init__(
            f"Manufacturer '{manufacturer_code}' is not supported",
            code="MANUFACTURER_NOT_SUPPORTED",
            details={'manufacturer': manufacturer_code},
        )

class DeviceNotFound(MicboardException):
    """Raised when device is not found."""

    def __init__(self, device_id: str, manufacturer_code: str):
        super().__init__(
            f"Device '{device_id}' not found for manufacturer '{manufacturer_code}'",
            code="DEVICE_NOT_FOUND",
            details={'device_id': device_id, 'manufacturer': manufacturer_code},
        )

class APIError(MicboardException):
    """Raised when API call fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
    ):
        super().__init__(
            message,
            code="API_ERROR",
            details={'status_code': status_code, 'response': response_body},
        )
```

### 9.2 Structured Logging

**File**: `micboard/logging.py` (NEW)
```python
"""Logging configuration with structured logging."""
import logging
import json
from typing import Any, Dict

class StructuredFormatter(logging.Formatter):
    """Format logs as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            log_obj.update(record.extra_fields)

        # Add exception info if present
        if record.exc_info:
            log_obj['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_obj)

def get_logger(name: str) -> logging.Logger:
    """Get structured logger."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger

# Usage
logger = get_logger(__name__)

def log_with_context(
    message: str,
    *,
    level: str = 'info',
    **kwargs,
) -> None:
    """Log with additional context."""
    record = logging.LogRecord(
        name='micboard',
        level=getattr(logging, level.upper()),
        pathname='',
        lineno=0,
        msg=message,
        args=(),
        exc_info=None,
    )
    record.extra_fields = kwargs
    logger.handle(record)
```

### 9.3 Error Handler Middleware

**File**: `micboard/middleware/error_handler.py` (NEW)
```python
"""Middleware for handling exceptions."""
import logging
from django.http import JsonResponse
from django.utils.decorators import sync_and_async_middleware

from ..exceptions import MicboardException

logger = logging.getLogger(__name__)

@sync_and_async_middleware
def error_handler_middleware(get_response):
    """Handle exceptions and return JSON responses."""

    def middleware(request):
        try:
            response = get_response(request)
            return response
        except MicboardException as e:
            logger.warning(
                f"MicboardException: {e.message}",
                extra={'code': e.code, 'details': e.details},
            )
            return JsonResponse(
                {
                    'error': e.message,
                    'code': e.code,
                    'details': e.details,
                },
                status=400,
            )
        except Exception as e:
            logger.exception("Unexpected error")
            return JsonResponse(
                {
                    'error': 'Internal server error',
                    'code': 'INTERNAL_ERROR',
                },
                status=500,
            )

    return middleware
```

---

## 10. Database Query Optimization

### 10.1 Query Analysis & Optimization

**File**: `tests/test_query_optimization.py` (NEW)
```python
"""Tests for database query optimization."""
import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection

@pytest.mark.django_db
class TestQueryOptimization:
    """Test query counts are minimal."""

    def test_receiver_list_queries(self, django_db_setup):
        """Test receiver list uses select_related."""
        ReceiverFactory.create_batch(10)

        with CaptureQueriesContext(connection) as ctx:
            list(Device.objects.filter(device_type='receiver'))

        # Should use select_related, so ~2 queries
        assert len(ctx) <= 2, f"Expected ≤2 queries, got {len(ctx)}"

    def test_location_summary_queries(self, django_db_setup):
        """Test location summary is optimized."""
        location = LocationFactory()
        ReceiverFactory.create_batch(5, location=location)

        with CaptureQueriesContext(connection) as ctx:
            receivers = location.receiver_set.select_related('manufacturer')
            list(receivers)

        # Should be exactly 1 query with select_related
        assert len(ctx) <= 1, f"Expected ≤1 query, got {len(ctx)}"
```

### 10.2 Manager Optimization

**File**: `micboard/models/managers.py` (UPDATE)
```python
"""Optimized database managers."""
from django.db import models

class ReceiverQuerySet(models.QuerySet):
    """QuerySet with optimizations."""

    def with_related(self):
        """Load related objects."""
        return self.select_related(
            'manufacturer',
            'location',
        ).prefetch_related(
            'tags',
        )

    def online(self):
        """Filter to online devices."""
        return self.filter(is_online=True)

    def low_battery(self, threshold: int = 20):
        """Filter to low battery devices."""
        return self.filter(battery_level__lt=threshold)

class ReceiverManager(models.Manager):
    """Manager for Receiver model."""

    def get_queryset(self):
        """Return optimized queryset."""
        return ReceiverQuerySet(self.model).with_related()
```

---

## 11. Secrets & Configuration Management

### 11.1 Environment Variable Handling

**File**: `micboard/settings.py` (Example)
```python
"""Django settings using environment variables."""
import os
from pathlib import Path

# Use environment variables with defaults
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
DEBUG = os.environ.get('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost').split(',')

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'micboard'),
        'USER': os.environ.get('DB_USER', 'postgres'),
        'PASSWORD': os.environ.get('DB_PASSWORD', ''),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# Cache
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
    }
}

# API Keys (use secrets manager in production)
SHURE_API_KEY = os.environ.get('SHURE_API_KEY')
SENNHEISER_API_KEY = os.environ.get('SENNHEISER_API_KEY')

# Ensure required settings in production
if not DEBUG:
    assert SECRET_KEY != 'dev-key-change-in-production'
    assert SHURE_API_KEY is not None
```

### 11.2 Secrets File Template

**File**: `.env.example` (NEW)
```bash
# Django
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DB_NAME=micboard
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432

# Redis/Cache
REDIS_URL=redis://127.0.0.1:6379/1

# Manufacturer APIs
SHURE_API_KEY=your-shure-api-key
SENNHEISER_API_KEY=your-sennheiser-api-key

# Logging
LOG_LEVEL=INFO

# Email (optional)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

---

## 12. Release Checklist & Deployment

### 12.1 Pre-Release Verification

**File**: `RELEASE_CHECKLIST.md` (NEW)
```markdown
# Release Checklist - v25.02.15

## Code Quality
- [ ] All tests passing: `pytest tests/ --cov=micboard --cov-fail-under=95`
- [ ] Coverage ≥95%: `coverage report`
- [ ] Linting passes: `uvx pre-commit run --all-files`
- [ ] Type checking: `mypy micboard --ignore-missing-imports`
- [ ] Security scan: `bandit -r micboard`
- [ ] No breaking changes documented

## Documentation
- [ ] README.md updated
- [ ] CHANGELOG.md entries added
- [ ] API docs generated: `python manage.py spectacular --file schema.yml`
- [ ] Deployment guide reviewed
- [ ] Migration steps documented (if applicable)

## Version & Build
- [ ] Version bumped to v25.02.15 (CalVer)
- [ ] `__version__.py` updated
- [ ] `pyproject.toml` version updated
- [ ] Build successful: `python -m build`
- [ ] Wheel inspected

## Testing in Staging
- [ ] Deployed to staging
- [ ] Smoke tests passed
- [ ] API endpoints responding
- [ ] WebSocket connections working
- [ ] Database migrations successful

## Release
- [ ] GitHub release drafted
- [ ] PyPI upload tested with `twine check dist/*`
- [ ] Release notes reviewed
- [ ] Notification prepared
- [ ] Rollback plan documented

## Post-Release
- [ ] Pushed to PyPI: `twine upload dist/*`
- [ ] GitHub release published
- [ ] Announcement posted
- [ ] Monitor error rates (first 24h)
- [ ] Update documentation links
```

### 12.2 Deployment Guide

**File**: `docs/DEPLOYMENT.md` (NEW)
```markdown
# Deployment Guide

## Prerequisites
- Python 3.9+
- PostgreSQL 12+
- Redis 6+
- Docker (optional)

## Installation

### From PyPI
```bash
pip install django-micboard
```

### From Source
```bash
git clone https://github.com/yourusername/django-micboard.git
pip install -e ./django-micboard
```

## Configuration

### 1. Add to Django INSTALLED_APPS
```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    # ...
    'channels',  # Required for WebSocket
    'micboard',
]
```

### 2. Set Environment Variables
```bash
export SECRET_KEY="your-secret-key"
export DEBUG=False
export SHURE_API_KEY="your-shure-key"
export SENNHEISER_API_KEY="your-sennheiser-key"
```

### 3. Run Migrations
```bash
python manage.py migrate micboard
```

### 4. Start Services
```bash
# API server
daphne -b 0.0.0.0 -p 8000 demo.asgi:application

# Polling task (alternative to Django-Q)
python manage.py poll_devices --interval 300

# Or with Django-Q
python manage.py qcluster
```

## Docker Deployment

See `demo/docker-compose.yml` for complete example.

```bash
docker-compose up -d
```

## Monitoring

### Health Check Endpoint
```bash
curl http://localhost:8000/api/health/
```

### Logs
```bash
docker-compose logs -f micboard
```

## Troubleshooting

### WebSocket Issues
- Check ASGI configuration
- Verify Redis is running
- Check firewall rules

### API Errors
- Check logs: `tail -f logs/micboard.log`
- Verify manufacturer credentials
- Run: `python manage.py check`
```

---

## Summary & Timeline

### Phase 2.1 Implementation Timeline

| Week | Focus | Deliverables |
|------|-------|--------------|
| 1 | Service layer | Contracts, DI container, base services |
| 2 | Remove signals | Refactor existing signals → services |
| 3 | Test suite | Service tests, edge cases, 95%+ coverage |
| 4 | Type hints | MyPy strict mode, py.typed, ADRs |
| 5 | API docs | OpenAPI/Swagger, endpoint docs |
| 6 | Release setup | CalVer, versioning, CI/CD workflows |
| 7 | Error handling | Exceptions, middleware, logging |
| 8 | Deployment | Docs, checklist, release v25.02.15 |

### Success Criteria

✅ 95%+ code coverage maintained
✅ All signals minimized (only cache cleanup remains)
✅ Type hints enforced via MyPy
✅ Service layer with clear contracts
✅ ADRs documented
✅ API fully documented
✅ CalVer versioning working
✅ CI/CD pipelines green
✅ Deployment documented
✅ Ready for production release (v25.02.15)

---

**Status**: Phase 2.1 Production Readiness Refactor
**Target**: v25.02.15 Release (February 15, 2025)
**Priority**: High - Gate for v1.0 Release

🚀 Ready to implement!
