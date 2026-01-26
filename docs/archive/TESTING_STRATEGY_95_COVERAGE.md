# Enhanced Testing Strategy - 95%+ Coverage

## Testing Framework & Setup

### Prerequisites
- pytest
- pytest-django
- pytest-cov
- factory-boy
- responses (for mocking HTTP)
- freezegun (for time mocking)

### Installation
```bash
pip install -e ".[dev,test]"
```

---

## Test Organization

```
tests/
├── conftest.py                 # Global fixtures and configuration
├── fixtures/
│   ├── __init__.py
│   ├── devices.py              # Device test data
│   ├── manufacturers.py        # Mock API responses
│   └── locations.py            # Location test data
├── unit/
│   ├── test_models.py          # Model tests
│   ├── test_managers.py        # Manager tests
│   ├── test_validators.py      # Validator tests
│   └── test_utils.py           # Utility tests
├── services/
│   ├── test_device_service.py
│   ├── test_sync_service.py
│   ├── test_location_service.py
│   └── test_health_service.py
├── api/
│   ├── test_viewsets.py
│   ├── test_filters.py
│   └── test_permissions.py
├── integration/
│   ├── test_device_workflow.py
│   ├── test_location_workflow.py
│   └── test_sync_workflow.py
├── e2e/
│   ├── test_full_sync_cycle.py
│   ├── test_api_flows.py
│   └── test_websocket_updates.py
└── performance/
    ├── test_query_count.py
    └── test_response_times.py
```

---

## Configuration

### pytest.ini
```ini
[pytest]
DJANGO_SETTINGS_MODULE = tests.settings
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --strict-markers
    --tb=short
    --disable-warnings
    --cov=micboard
    --cov-report=term-missing
    --cov-report=html
    --cov-report=xml
    --cov-fail-under=95
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
    slow: Slow tests
    performance: Performance tests
```

### conftest.py
```python
"""Global test configuration and fixtures."""
import os
import django
from pathlib import Path

import pytest
from django.conf import settings
from factory.django import DjangoModelFactory

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')
django.setup()

from micboard.models import Device, Location, Manufacturer

# ============ Factories ============

class ManufacturerFactory(DjangoModelFactory):
    """Manufacturer factory."""
    code = 'shure'
    name = 'Shure'
    is_active = True

    class Meta:
        model = Manufacturer

class LocationFactory(DjangoModelFactory):
    """Location factory."""
    name = 'Main Stage'
    description = 'Main performance area'

    class Meta:
        model = Location

class ReceiverFactory(DjangoModelFactory):
    """Receiver device factory."""
    device_id = 'rx_0001'
    name = 'Receiver 1'
    device_type = 'receiver'
    manufacturer = factory.SubFactory(ManufacturerFactory)
    location = factory.SubFactory(LocationFactory)
    is_online = True
    battery_level = 85
    signal_strength = -50

    class Meta:
        model = Device

# ============ Fixtures ============

@pytest.fixture
def manufacturer():
    """Create manufacturer."""
    return ManufacturerFactory()

@pytest.fixture
def location():
    """Create location."""
    return LocationFactory()

@pytest.fixture
def receiver(manufacturer, location):
    """Create receiver device."""
    return ReceiverFactory(
        manufacturer=manufacturer,
        location=location,
    )

@pytest.fixture
def multiple_receivers(manufacturer, location):
    """Create multiple receivers."""
    return ReceiverFactory.create_batch(5, manufacturer=manufacturer, location=location)

# ============ Mock Responses ============

@pytest.fixture
def mock_shure_device_response():
    """Mock Shure device API response."""
    return {
        'id': 'rx_0001',
        'name': 'Receiver 1',
        'battery': 85,
        'signal': -50,
        'status': 'online',
    }

@pytest.fixture
def mock_shure_devices_response():
    """Mock Shure devices list API response."""
    return {
        'devices': [
            {'id': 'rx_0001', 'name': 'Receiver 1', 'battery': 85},
            {'id': 'rx_0002', 'name': 'Receiver 2', 'battery': 92},
            {'id': 'tx_0001', 'name': 'Transmitter 1', 'battery': 78},
        ]
    }
```

---

## Unit Test Examples

### Model Tests
```python
"""Tests for models."""
import pytest
from django.db import IntegrityError
from django.utils import timezone

@pytest.mark.django_db
class TestDeviceModel:
    """Test Device model."""

    def test_create_device(self, manufacturer):
        """Test creating a device."""
        device = Device.objects.create(
            device_id='rx_0001',
            name='Receiver 1',
            manufacturer=manufacturer,
            device_type='receiver',
        )

        assert device.id is not None
        assert device.device_id == 'rx_0001'
        assert device.is_online is False
        assert device.battery_level is None

    def test_device_unique_constraint(self, manufacturer):
        """Test device_id + manufacturer uniqueness."""
        Device.objects.create(
            device_id='rx_0001',
            manufacturer=manufacturer,
            device_type='receiver',
        )

        with pytest.raises(IntegrityError):
            Device.objects.create(
                device_id='rx_0001',
                manufacturer=manufacturer,
                device_type='receiver',
            )

    def test_device_str_representation(self, receiver):
        """Test string representation."""
        assert str(receiver) == f"{receiver.name} ({receiver.device_id})"

    def test_device_battery_validation(self, receiver):
        """Test battery level validation."""
        receiver.battery_level = 101  # Invalid

        with pytest.raises(ValidationError):
            receiver.full_clean()
```

### Manager Tests
```python
"""Tests for managers."""
import pytest

@pytest.mark.django_db
class TestDeviceManager:
    """Test Device manager."""

    def test_get_online_devices(self, manufacturer):
        """Test filtering online devices."""
        Device.objects.create(
            device_id='rx_0001',
            manufacturer=manufacturer,
            is_online=True,
        )
        Device.objects.create(
            device_id='rx_0002',
            manufacturer=manufacturer,
            is_online=False,
        )

        online = Device.objects.filter(is_online=True)
        assert online.count() == 1
        assert online.first().device_id == 'rx_0001'

    def test_low_battery_filter(self, manufacturer):
        """Test low battery filtering."""
        Device.objects.create(
            device_id='rx_0001',
            manufacturer=manufacturer,
            battery_level=15,
        )
        Device.objects.create(
            device_id='rx_0002',
            manufacturer=manufacturer,
            battery_level=50,
        )

        low = Device.objects.filter(battery_level__lt=20)
        assert low.count() == 1
```

---

## Service Layer Tests

### DeviceService Tests
```python
"""Tests for DeviceService."""
import pytest
from unittest.mock import patch, MagicMock

from micboard.services import DeviceService
from micboard.services.contracts import ServiceStatus

@pytest.mark.django_db
class TestDeviceService:
    """Test DeviceService."""

    def test_get_device_success(self, receiver):
        """Test getting existing device."""
        service = DeviceService()
        result = service.get_device(receiver.device_id)

        assert result.status == ServiceStatus.SUCCESS
        assert result.data['device_id'] == receiver.device_id
        assert result.data['is_online'] is True

    def test_get_device_not_found(self):
        """Test getting non-existent device."""
        service = DeviceService()
        result = service.get_device('nonexistent')

        assert result.status == ServiceStatus.FAILURE
        assert 'not found' in result.error.lower()

    def test_update_device_state_success(self, receiver):
        """Test updating device state."""
        service = DeviceService()
        result = service.update_device_state(
            receiver.device_id,
            battery_level=50,
            signal_strength=-70,
        )

        assert result.status == ServiceStatus.SUCCESS

        receiver.refresh_from_db()
        assert receiver.battery_level == 50
        assert receiver.signal_strength == -70

    def test_update_device_state_invalid_battery(self, receiver):
        """Test validation in update."""
        service = DeviceService()
        result = service.update_device_state(
            receiver.device_id,
            battery_level=150,  # Invalid
        )

        assert result.status == ServiceStatus.FAILURE
        assert '0-100' in result.error

    def test_update_device_state_partial(self, receiver):
        """Test partial update."""
        original_signal = receiver.signal_strength
        service = DeviceService()

        result = service.update_device_state(
            receiver.device_id,
            battery_level=45,
        )

        assert result.status == ServiceStatus.SUCCESS
        receiver.refresh_from_db()
        assert receiver.battery_level == 45
        assert receiver.signal_strength == original_signal
```

### SynchronizationService Tests
```python
"""Tests for SynchronizationService."""
import pytest
from unittest.mock import patch, Mock

from micboard.services import SynchronizationService
from micboard.services.contracts import ServiceStatus

@pytest.mark.django_db
class TestSynchronizationService:
    """Test SynchronizationService."""

    @patch('micboard.manufacturers.get_manufacturer_plugin')
    def test_sync_device_success(self, mock_get_plugin, manufacturer, mock_shure_device_response):
        """Test successful device sync."""
        mock_plugin = Mock()
        mock_plugin.get_device.return_value = mock_shure_device_response
        mock_get_plugin.return_value = mock_plugin

        service = SynchronizationService()
        result = service.sync_device('shure', 'rx_0001')

        assert result.status == ServiceStatus.SUCCESS
        assert result.data['created'] is True
        assert result.data['device_id'] == 'rx_0001'

    @patch('micboard.manufacturers.get_manufacturer_plugin')
    def test_sync_all_devices(self, mock_get_plugin, manufacturer, mock_shure_devices_response):
        """Test syncing multiple devices."""
        mock_plugin = Mock()
        mock_plugin.get_devices.return_value = mock_shure_devices_response['devices']
        mock_plugin.get_device.side_effect = lambda x: next(
            d for d in mock_shure_devices_response['devices'] if d['id'] == x
        )
        mock_get_plugin.return_value = mock_plugin

        service = SynchronizationService()
        result = service.sync_all_devices('shure')

        assert result.status in (ServiceStatus.SUCCESS, ServiceStatus.PARTIAL)
        assert result.data['synced'] >= 1
```

---

## Integration Tests

### Workflow Tests
```python
"""Integration tests for workflows."""
import pytest
from unittest.mock import patch, Mock

@pytest.mark.django_db
@pytest.mark.integration
class TestDeviceWorkflow:
    """Test device creation and sync workflow."""

    @patch('micboard.manufacturers.get_manufacturer_plugin')
    def test_full_device_sync_workflow(
        self,
        mock_get_plugin,
        manufacturer,
        mock_shure_device_response,
    ):
        """Test complete device sync workflow."""
        # Mock manufacturer plugin
        mock_plugin = Mock()
        mock_plugin.get_device.return_value = mock_shure_device_response
        mock_get_plugin.return_value = mock_plugin

        from micboard.services import SynchronizationService, DeviceService

        # Step 1: Sync device
        sync_service = SynchronizationService()
        sync_result = sync_service.sync_device('shure', 'rx_0001')
        assert sync_result.status == ServiceStatus.SUCCESS

        # Step 2: Get device
        device_service = DeviceService()
        get_result = device_service.get_device('rx_0001')
        assert get_result.status == ServiceStatus.SUCCESS
        assert get_result.data['battery'] == 85

        # Step 3: Update device state
        update_result = device_service.update_device_state(
            'rx_0001',
            battery_level=75,
        )
        assert update_result.status == ServiceStatus.SUCCESS

        # Step 4: Verify update
        final_result = device_service.get_device('rx_0001')
        assert final_result.data['battery'] == 75
```

---

## E2E Tests

### API Endpoint Tests
```python
"""End-to-end API tests."""
import pytest
from django.test import Client

@pytest.mark.django_db
@pytest.mark.e2e
class TestAPIEndpoints:
    """Test API endpoints."""

    def test_receiver_list_endpoint(self, multiple_receivers):
        """Test receiver list endpoint."""
        client = Client()
        response = client.get('/api/receivers/')

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

    def test_receiver_detail_endpoint(self, receiver):
        """Test receiver detail endpoint."""
        client = Client()
        response = client.get(f'/api/receivers/{receiver.id}/')

        assert response.status_code == 200
        data = response.json()
        assert data['device_id'] == receiver.device_id
```

---

## Coverage Report

### Running Tests with Coverage
```bash
# Run all tests with coverage
pytest tests/ --cov=micboard --cov-report=html

# Run specific test file
pytest tests/services/test_device_service.py -v

# Run specific test
pytest tests/services/test_device_service.py::TestDeviceService::test_get_device_success -v

# Show missing coverage
pytest tests/ --cov=micboard --cov-report=term-missing

# Generate coverage badge
coverage-badge -o coverage.svg
```

### Expected Coverage
```
micboard/models/        98%
micboard/services/      96%
micboard/api/           92%
micboard/managers.py    99%
micboard/exceptions.py  95%
TOTAL                   95%
```

---

## Performance Tests

### Query Count Tests
```python
"""Performance tests for database queries."""
import pytest
from django.test.utils import CaptureQueriesContext
from django.db import connection

@pytest.mark.django_db
@pytest.mark.performance
class TestQueryOptimization:
    """Test database query optimization."""

    def test_receiver_list_query_count(self, multiple_receivers):
        """Test receiver list uses minimal queries."""
        with CaptureQueriesContext(connection) as ctx:
            list(Device.objects.filter(device_type='receiver'))

        # Should be 1-2 queries max
        assert len(ctx) <= 2

    def test_location_summary_query_count(self, location):
        """Test location summary is optimized."""
        from factory.django import DjangoModelFactory
        ReceiverFactory = type('ReceiverFactory', (DjangoModelFactory,), {
            'Meta': type('Meta', (), {'model': Device})
        })
        ReceiverFactory.create_batch(5, location=location)

        with CaptureQueriesContext(connection) as ctx:
            receivers = location.receiver_set.select_related('manufacturer')
            list(receivers)

        assert len(ctx) <= 1
```

---

## Continuous Coverage Monitoring

### GitHub Actions Integration
```yaml
# .github/workflows/coverage.yml
name: Coverage

on: [push, pull_request]

jobs:
  coverage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -e ".[dev,test]"
      - run: pytest tests/ --cov=micboard --cov-report=xml
      - uses: codecov/codecov-action@v3
```

---

## Running Full Test Suite

```bash
# Run all tests
pytest tests/ -v

# Run with detailed output
pytest tests/ -vv --tb=long

# Run only unit tests
pytest tests/unit/ -v

# Run only integration tests
pytest tests/integration/ -v

# Run only e2e tests
pytest tests/e2e/ -v

# Run with markers
pytest tests/ -m "unit" -v

# Run tests matching pattern
pytest tests/ -k "device" -v

# Run with parallel execution (if installed)
pytest tests/ -n auto
```

---

## Success Criteria

✅ Overall coverage ≥95%
✅ All modules tested (unit + integration + e2e)
✅ Edge cases covered
✅ Performance validated (queries, response times)
✅ No test dependencies
✅ Fixtures isolated per test
✅ Mocks used for external APIs
✅ CI/CD gates enforced

---

**Next**: See PRODUCTION_READINESS_REFACTOR.md for full context
