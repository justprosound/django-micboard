
# Services Layer Refactoring Guide

## Overview

This guide walks through refactoring existing django-micboard code to use the new services layer. The goal is to extract business logic from views, models, and signals into reusable, testable services.

## Phase 1: Service Extraction Strategy

### Step 1: Identify Monolithic Code

Look for code that:
- Repeats queries across multiple views or commands
- Contains complex business logic in views
- Has tight coupling between models and views
- Uses signals for core business logic (not just audit/notification)

Common patterns:
```python
# ❌ Bad: Logic in view
def receiver_status_view(request, receiver_id):
    receiver = Receiver.objects.get(id=receiver_id)
    receiver.online = True
    receiver.save()
    return Response({'status': 'updated'})
```

### Step 2: Extract to Service

```python
# ✅ Good: Logic in service
from micboard.services import DeviceService

def receiver_status_view(request, receiver_id):
    receiver = Receiver.objects.get(id=receiver_id)
    DeviceService.sync_device_status(device_obj=receiver, online=True)
    return Response({'status': 'updated'})
```

### Step 3: Update Related Code

Update views, commands, and signals to use services.

## Refactoring Examples

### Example 1: Device Status Synchronization

#### Before (spread across views and commands):

**views.py:**
```python
from rest_framework.response import Response
from rest_framework.views import APIView
from micboard.models import Receiver

class ReceiverStatusView(APIView):
    def post(self, request, receiver_id):
        receiver = Receiver.objects.get(id=receiver_id)
        receiver.online = request.data.get('online', False)
        receiver.battery_level = request.data.get('battery_level')
        receiver.save()
        return Response({'status': 'updated'})
```

**management/commands/poll_devices.py:**
```python
from django.core.management.base import BaseCommand
from micboard.models import Receiver
from micboard.manufacturers import get_manufacturer_plugin

class Command(BaseCommand):
    def handle(self, *args, **options):
        plugin = get_manufacturer_plugin('shure')
        devices = plugin.get_devices()

        for device_data in devices:
            receiver = Receiver.objects.get(device_id=device_data['id'])
            receiver.online = device_data['online']
            receiver.battery_level = device_data['battery']
            receiver.save()
```

#### After (using DeviceService):

**views.py:**
```python
from rest_framework.response import Response
from rest_framework.views import APIView
from micboard.models import Receiver
from micboard.services import DeviceService

class ReceiverStatusView(APIView):
    def post(self, request, receiver_id):
        receiver = Receiver.objects.get(id=receiver_id)

        if 'online' in request.data:
            DeviceService.sync_device_status(
                device_obj=receiver,
                online=request.data['online']
            )
        if 'battery_level' in request.data:
            DeviceService.sync_device_battery(
                device_obj=receiver,
                battery_level=request.data['battery_level']
            )

        receiver.refresh_from_db()
        return Response({'status': 'updated'})
```

**management/commands/poll_devices.py:**
```python
from django.core.management.base import BaseCommand
from micboard.models import Receiver
from micboard.manufacturers import get_manufacturer_plugin
from micboard.services import DeviceService

class Command(BaseCommand):
    def handle(self, *args, **options):
        plugin = get_manufacturer_plugin('shure')
        devices = plugin.get_devices()

        for device_data in devices:
            receiver = Receiver.objects.get(device_id=device_data['id'])
            DeviceService.sync_device_status(
                device_obj=receiver,
                online=device_data['online']
            )
            DeviceService.sync_device_battery(
                device_obj=receiver,
                battery_level=device_data['battery']
            )
```

### Example 2: Assignment Management

#### Before (logic in views):

```python
class CreateAssignmentView(APIView):
    def post(self, request):
        user = request.user
        device_id = request.data['device_id']
        alert_enabled = request.data.get('alert_enabled', True)

        # Check if assignment exists
        if Assignment.objects.filter(user=user, device_id=device_id).exists():
            return Response({'error': 'Already assigned'}, status=400)

        assignment = Assignment.objects.create(
            user=user,
            device_id=device_id,
            alert_enabled=alert_enabled
        )

        # Broadcast notification
        notify_assignment_created(assignment)

        return Response(AssignmentSerializer(assignment).data)
```

#### After (using AssignmentService):

```python
from micboard.services import AssignmentService
from micboard.models import Receiver

class CreateAssignmentView(APIView):
    def post(self, request):
        user = request.user
        device_id = request.data['device_id']
        device = Receiver.objects.get(id=device_id)

        try:
            assignment = AssignmentService.create_assignment(
                user=user,
                device=device,
                alert_enabled=request.data.get('alert_enabled', True)
            )
        except ValueError as e:
            return Response({'error': str(e)}, status=400)

        # Broadcast notification
        notify_assignment_created(assignment)

        return Response(AssignmentSerializer(assignment).data)
```

### Example 3: Connection Health Monitoring

#### Before (logic scattered):

```python
# In management command
from django.utils.timezone import now
from datetime import timedelta

def check_connections():
    for conn in RealTimeConnection.objects.filter(status='connected'):
        timeout = now() - timedelta(seconds=60)
        if not conn.last_heartbeat or conn.last_heartbeat < timeout:
            conn.status = 'error'
            conn.save()
            log_error(f"Connection {conn.id} unhealthy")
```

#### After (using ConnectionHealthService):

```python
from micboard.services import ConnectionHealthService

def check_connections():
    unhealthy = ConnectionHealthService.get_unhealthy_connections(
        heartbeat_timeout_seconds=60
    )
    for conn in unhealthy:
        ConnectionHealthService.update_connection_status(
            connection=conn,
            status='error'
        )
        log_error(f"Connection {conn.id} unhealthy")
```

## Migration Checklist

- [ ] **Identify all views that perform model operations**
  - Search for `.save()`, `.delete()`, `.create()`, `.update()` calls
  - Move logic to appropriate service methods

- [ ] **Extract repeated query patterns**
  - Search for `.filter()` and `.get()` calls across files
  - Create service methods like `get_active_receivers()`, `get_device_by_ip()`

- [ ] **Refactor management commands**
  - Update `poll_devices.py` to use services
  - Update other management commands

- [ ] **Update signal handlers**
  - Move core business logic out of signals
  - Use signals only for cross-app notifications (audit logs, etc.)

- [ ] **Refactor serializers**
  - Ensure serializers call services for complex operations
  - Don't duplicate business logic in serializer methods

- [ ] **Update tests**
  - Write tests for service methods
  - Update existing view/command tests to mock services

## Code Review Checklist

When reviewing refactored code:

- [ ] All business logic is in services, not views
- [ ] Services use keyword-only parameters
- [ ] Services have type hints and docstrings
- [ ] Views/commands/signals call services via clear interface
- [ ] Error handling is appropriate (services raise exceptions, views handle them)
- [ ] No circular imports between models, views, and services
- [ ] Tests for new service methods exist

## Common Pitfalls

### ❌ Don't: Put serializer logic in services

```python
# BAD
class DeviceService:
    @staticmethod
    def get_device_data(device_id):
        device = Receiver.objects.get(id=device_id)
        return {
            'id': device.id,
            'name': device.name,
            'online': device.online
        }  # This is serializer work, not service work
```

### ✅ Do: Return domain objects

```python
# GOOD
class DeviceService:
    @staticmethod
    def get_device(*, device_id: int) -> Receiver:
        return Receiver.objects.get(id=device_id)

# In view/serializer:
device = DeviceService.get_device(device_id=device_id)
serializer = ReceiverSerializer(device)
```

### ❌ Don't: Create multiple services for one domain

```python
# BAD: Scattered across files
class ReceiverService:
    def get_receivers(self): ...

class ReceiverStatusService:
    def update_status(self): ...

class ReceiverBatteryService:
    def update_battery(self): ...
```

### ✅ Do: Consolidate related logic

```python
# GOOD: All device logic in one place
class DeviceService:
    @staticmethod
    def get_active_receivers(self): ...

    @staticmethod
    def sync_device_status(self, ...): ...

    @staticmethod
    def sync_device_battery(self, ...): ...
```

### ❌ Don't: Make services depend on HTTP objects

```python
# BAD
class DeviceService:
    @staticmethod
    def create_device(request):  # Request object!
        user = request.user
        ...
```

### ✅ Do: Pass extracted data

```python
# GOOD
class DeviceService:
    @staticmethod
    def create_device(*, user: User, name: str):
        ...

# In view:
device = DeviceService.create_device(user=request.user, name=request.data['name'])
```

## Integration with Existing Code

### Step 1: Add services without breaking existing code

Services are additive—you can introduce them gradually without removing old code.

```python
# Old code still works
receiver = Receiver.objects.filter(active=True).first()

# New code uses service
receiver = DeviceService.get_active_receivers().first()
```

### Step 2: Gradually migrate

1. New features use services
2. When updating old code, use services
3. Eventually, direct model access becomes rare

### Step 3: Update internal references

```python
# management/commands/poll_devices.py
from micboard.services import (
    ManufacturerService,
    DeviceService,
    ConnectionHealthService
)

class Command(BaseCommand):
    def handle(self, *args, **options):
        # Use services instead of direct model access
        manufacturers = ManufacturerService.get_active_manufacturers()
        for mfg_config in manufacturers:
            result = ManufacturerService.sync_devices_for_manufacturer(
                manufacturer_code=mfg_config.manufacturer_code
            )
            self.stdout.write(f"Synced: {result}")
```

## Testing Refactored Code

### Service Unit Tests

```python
from django.test import TestCase
from micboard.services import DeviceService
from micboard.models import Receiver

class DeviceServiceTestCase(TestCase):
    def setUp(self):
        self.receiver = Receiver.objects.create(
            ip_address="192.168.1.1",
            active=True,
            online=False
        )

    def test_sync_device_status(self):
        DeviceService.sync_device_status(device_obj=self.receiver, online=True)
        self.receiver.refresh_from_db()
        self.assertTrue(self.receiver.online)

    def test_get_active_receivers(self):
        inactive_receiver = Receiver.objects.create(
            ip_address="192.168.1.2",
            active=False
        )
        active = DeviceService.get_active_receivers()
        self.assertEqual(active.count(), 1)
        self.assertIn(self.receiver, active)
        self.assertNotIn(inactive_receiver, active)
```

### View Tests with Mocked Services

```python
from django.test import TestCase
from unittest.mock import patch, MagicMock
from rest_framework.test import APIRequestFactory
from myapp.views import ReceiverStatusView

class ReceiverStatusViewTestCase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = ReceiverStatusView.as_view()

    @patch('micboard.services.DeviceService.sync_device_status')
    def test_receiver_status_view(self, mock_sync):
        request = self.factory.post('/receivers/1/status/', {'online': True})
        response = self.view(request, receiver_id=1)

        mock_sync.assert_called_once()
        self.assertEqual(response.status_code, 200)
```

## See Also

- [Services Layer Documentation](services-layer.md)
- [Architecture Overview](architecture.md)
- [Contributing Guidelines](../CONTRIBUTING.md)
