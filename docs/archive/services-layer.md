
# Django Micboard Services Layer

## Overview

The services layer provides business logic abstraction for django-micboard, enabling:

- **Decoupling**: Services are independent from views, serializers, and signals
- **Reusability**: Services can be used in management commands, views, background tasks, or signals
- **Testability**: Plain Python classes with explicit methods and type hints
- **Maintainability**: Centralized business logic reduces duplication

## Architecture

```
Views/API
   ↓
Services (business logic)
   ↓
Models (data persistence)
```

Services coordinate operations on models and external systems (manufacturer APIs, etc.)
without being tightly coupled to any specific consumer.

## Available Services

### DeviceService

Manages receiver and transmitter devices, status synchronization, and queries.

```python
from micboard.services import DeviceService

# Get active devices
receivers = DeviceService.get_active_receivers()
transmitters = DeviceService.get_active_transmitters()

# Update device status
DeviceService.sync_device_status(device_obj=receiver, online=True)
DeviceService.sync_device_battery(device_obj=transmitter, battery_level=75)

# Find device by IP
device = DeviceService.get_device_by_ip(ip_address="192.168.1.100")

# Search devices
results = DeviceService.search_devices(query="micboard-01")

# Get statistics
stats = DeviceService.count_online_devices()  # {'receivers': 5, 'transmitters': 12}
```

### AssignmentService

Manages user-device assignments and alert preferences.

```python
from micboard.services import AssignmentService
from django.contrib.auth.models import User
from micboard.models import Receiver

user = User.objects.get(username="john")
receiver = Receiver.objects.first()

# Create assignment
assignment = AssignmentService.create_assignment(
    user=user,
    device=receiver,
    alert_enabled=True,
    notes="Main stage mic"
)

# Update assignment
AssignmentService.update_assignment(
    assignment=assignment,
    alert_enabled=False
)

# Query assignments
user_assignments = AssignmentService.get_user_assignments(user=user)
device_assignments = AssignmentService.get_device_assignments(device_id=receiver.id)

# Get users with alerts
alert_users = AssignmentService.get_users_with_alerts(device_id=receiver.id)

# Check assignment existence
has_it = AssignmentService.has_assignment(user_id=user.id, device_id=receiver.id)
```

### ManufacturerService

Orchestrates communication with manufacturer APIs and device synchronization.

```python
from micboard.services import ManufacturerService

# Get plugin
plugin = ManufacturerService.get_plugin(manufacturer_code='shure')

# Sync all devices from a manufacturer
result = ManufacturerService.sync_devices_for_manufacturer(
    manufacturer_code='shure'
)
# Returns: {
#     'success': bool,
#     'devices_added': int,
#     'devices_updated': int,
#     'devices_removed': int,
#     'errors': list[str]
# }

# Get active manufacturers
manufacturers = ManufacturerService.get_active_manufacturers()

# Test connection
test_result = ManufacturerService.test_manufacturer_connection(
    manufacturer_code='shure'
)
# Returns: {
#     'success': bool,
#     'message': str,
#     'response_time_ms': float | None
# }

# Get device status
status = ManufacturerService.get_device_status(
    manufacturer_code='shure',
    device_id='rxstat-1234'
)
```

### ConnectionHealthService

Monitors real-time connection status, health, and uptime.

```python
from micboard.services import ConnectionHealthService

# Create connection
conn = ConnectionHealthService.create_connection(
    manufacturer_code='shure',
    connection_type='websocket',
    status='connecting'
)

# Update status
ConnectionHealthService.update_connection_status(
    connection=conn,
    status='connected'
)

# Record heartbeat
ConnectionHealthService.record_heartbeat(connection=conn)

# Record error
ConnectionHealthService.record_error(
    connection=conn,
    error_message="Connection timeout"
)

# Check health
is_healthy = ConnectionHealthService.is_healthy(
    connection=conn,
    heartbeat_timeout_seconds=60
)

# Get statistics
stats = ConnectionHealthService.get_connection_stats()
# Returns: {
#     'total_connections': int,
#     'active_connections': int,
#     'error_connections': int,
#     'avg_error_count': float | None,
#     'by_manufacturer': dict[str, int]
# }

# Get uptime
uptime = ConnectionHealthService.get_connection_uptime(connection=conn)
```

### LocationService

Manages locations and location-based device organization.

```python
from micboard.services import LocationService

# Create location
location = LocationService.create_location(
    name="Main Stage",
    description="Main stage area"
)

# Update location
LocationService.update_location(
    location=location,
    name="Main Stage Left"
)

# Get all locations
all_locations = LocationService.get_all_locations()

# Get locations with device counts
locations_with_counts = LocationService.get_location_device_counts()

# Assign device to location
DeviceService.get_active_receivers().first()  # Get a receiver
device = receiver
LocationService.assign_device_to_location(device=device, location=location)

# Get devices in location
devices = LocationService.get_devices_in_location(location=location)
```

### DiscoveryService

Handles device discovery via CIDR, mDNS, and manual registration.

```python
from micboard.services import DiscoveryService

# Create discovery task
task = DiscoveryService.create_discovery_task(
    name="Main Network",
    discovery_type='cidr',
    target='192.168.1.0/24',
    enabled=True
)

# Get enabled tasks
tasks = DiscoveryService.get_enabled_discovery_tasks()

# Execute discovery
result = DiscoveryService.execute_discovery(task=task)

# Register discovered device
device = DiscoveryService.register_discovered_device(
    ip_address='192.168.1.50',
    device_type='receiver',
    name='New Receiver',
    manufacturer_code='shure'
)

# Delete task
DiscoveryService.delete_discovery_task(task=task)
```

## Usage Patterns

### In Management Commands

```python
from django.core.management.base import BaseCommand
from micboard.services import ManufacturerService, ConnectionHealthService

class Command(BaseCommand):
    def handle(self, *args, **options):
        # Sync all devices
        result = ManufacturerService.sync_devices_for_manufacturer(
            manufacturer_code='shure'
        )
        self.stdout.write(f"Synced: {result}")

        # Check connection health
        unhealthy = ConnectionHealthService.get_unhealthy_connections()
        for conn in unhealthy:
            self.stdout.write(f"Unhealthy: {conn}")
```

### In Views

```python
from django.shortcuts import render
from micboard.services import DeviceService, AssignmentService

def device_list_view(request):
    devices = DeviceService.get_active_receivers()
    assignments = AssignmentService.get_user_assignments(user=request.user)

    return render(request, 'devices.html', {
        'devices': devices,
        'assignments': assignments
    })
```

### In Signals

```python
from django.db.models.signals import post_save
from django.dispatch import receiver
from micboard.models import Receiver
from micboard.services import ConnectionHealthService

@receiver(post_save, sender=Receiver)
def on_receiver_created(sender, instance, created, **kwargs):
    if created:
        # Could create connection tracking here if needed
        pass
```

### In Background Tasks (Django-Q)

```python
from django_q.tasks import schedule
from micboard.services import ManufacturerService

def sync_all_devices():
    """Background task to sync devices from all manufacturers."""
    manufacturers = ManufacturerService.get_active_manufacturers()

    for mfg in manufacturers:
        result = ManufacturerService.sync_devices_for_manufacturer(
            manufacturer_code=mfg.manufacturer_code
        )
        print(f"Synced {mfg.manufacturer_code}: {result}")

# Schedule it
schedule('myapp.tasks.sync_all_devices', repeat=-1, repeat_until=None)
```

## Design Principles

### 1. Explicit Parameters

All parameters are keyword-only to enforce clarity:

```python
# ✅ Good
DeviceService.sync_device_status(device_obj=receiver, online=True)

# ❌ Bad (not supported)
DeviceService.sync_device_status(receiver, True)
```

### 2. Type Hints

All services use type hints for parameters and return values:

```python
@staticmethod
def create_assignment(
    *,
    user: User,
    device: Receiver | Transmitter,
    *,
    alert_enabled: bool = True,
    notes: str = ""
) -> Assignment:
    ...
```

### 3. Error Handling

Services raise clear exceptions for invalid operations:

```python
try:
    assignment = AssignmentService.create_assignment(
        user=user,
        device=device
    )
except ValueError as e:
    # Handle duplicate assignment
    print(f"Error: {e}")
```

### 4. Minimal Side Effects

Services return domain objects or DTOs, not HTTP responses or serialized data:

```python
# Service returns model instance
assignment = AssignmentService.create_assignment(...)

# View/API is responsible for serialization
serializer = AssignmentSerializer(assignment)
return Response(serializer.data)
```

### 5. DRY Principle

Repeated logic is centralized:

```python
# Instead of duplicating device lookup across views and management commands
device = DeviceService.get_device_by_ip(ip_address="192.168.1.100")
```

## Testing Services

Services can be tested independently of views or serializers:

```python
from django.test import TestCase
from micboard.services import DeviceService

class DeviceServiceTestCase(TestCase):
    def test_get_active_receivers(self):
        receivers = DeviceService.get_active_receivers()
        self.assertEqual(receivers.count(), 0)

        # Create a receiver
        Receiver.objects.create(ip_address="192.168.1.1", active=True)

        receivers = DeviceService.get_active_receivers()
        self.assertEqual(receivers.count(), 1)
```

## Migration from Views to Services

### Before (logic in view):

```python
def device_list(request):
    receivers = Receiver.objects.filter(active=True)
    transmitters = Transmitter.objects.filter(active=True)

    devices = list(receivers) + list(transmitters)

    return Response({'devices': devices})
```

### After (logic in service):

```python
def device_list(request):
    receivers = DeviceService.get_active_receivers()
    transmitters = DeviceService.get_active_transmitters()

    devices = list(receivers) + list(transmitters)

    return Response({'devices': devices})
```

Even better, add a service method:

```python
def device_list(request):
    stats = DeviceService.count_online_devices()
    return Response(stats)
```

## Future Enhancements

- Add caching at service layer for frequently accessed queries
- Implement pagination helpers
- Add bulk operation methods
- Create transaction wrappers for complex multi-model operations
- Add event emitters for cross-service communication
