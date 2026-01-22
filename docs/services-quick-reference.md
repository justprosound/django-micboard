# Services Quick Reference

Quick examples for using the new services layer in django-micboard.

## Import Services

```python
from micboard.services import (
    DeviceService,
    DiscoveryService,
    PollingService,
)
from micboard.models import Manufacturer
```

## Device Management

### Sync devices from API
```python
manufacturer = Manufacturer.objects.get(code='shure')
service = DeviceService(manufacturer)

# Pull devices from API, create/update Receiver models
created, updated = service.sync_devices_from_api()
print(f"Created: {created}, Updated: {updated}")
```

### Get active devices
```python
service = DeviceService(manufacturer)
devices = service.get_active_devices()

for device in devices:
    print(f"{device.name} - {device.ip} - Online: {device.is_online}")
```

### Update device state
```python
service = DeviceService(manufacturer)

# Mark device online
service.mark_online(device_id)

# Mark device offline
service.mark_offline(device_id)

# Update custom fields
service.update_device_state(device_id, {
    'name': 'New Name',
    'location': 'Room 101'
})
```

### Full polling (devices + transmitters)
```python
service = DeviceService(manufacturer)
result = service.poll_and_sync_all()

print(f"Devices created: {result['devices_created']}")
print(f"Devices updated: {result['devices_updated']}")
print(f"Transmitters synced: {result['transmitters_synced']}")
print(f"Errors: {result['errors']}")
```

## Polling Orchestration

### Poll all manufacturers
```python
service = PollingService()
results = service.poll_all_manufacturers()

print(f"Total devices: {results['summary']['total_devices']}")
print(f"Total transmitters: {results['summary']['total_transmitters']}")

for code, result in results['manufacturers'].items():
    print(f"{code}: {result['devices_created']} created, {result['devices_updated']} updated")
```

### Poll single manufacturer
```python
service = PollingService()
manufacturer = Manufacturer.objects.get(code='shure')
result = service.poll_manufacturer(manufacturer)

print(f"Status: {result.get('status', 'success')}")
print(f"Devices: {result['devices_created']} created, {result['devices_updated']} updated")
```

### Check polling health
```python
service = PollingService()
health = service.get_polling_health()

print(f"Overall status: {health['overall_status']}")
print(f"Total devices: {health['summary']['total_devices']}")
print(f"Online devices: {health['summary']['online_devices']}")

for code, mfr_health in health['manufacturers'].items():
    print(f"{code}: {mfr_health['online_devices']}/{mfr_health['active_devices']} online")
```

### Check API health
```python
service = PollingService()
manufacturer = Manufacturer.objects.get(code='shure')
health = service.check_api_health(manufacturer)

print(f"API status: {health['status']}")
print(f"Base URL: {health.get('base_url')}")
```

## Discovery Management

### Add IPs to discovery
```python
service = DiscoveryService()
manufacturer = Manufacturer.objects.get(code='shure')

# Add single IP
success = service.add_discovery_candidate(
    "172.21.1.100",
    manufacturer,
    source="manual"
)

# Add multiple IPs (iterate)
ips = ["172.21.1.100", "172.21.1.101", "172.21.1.102"]
for ip in ips:
    service.add_discovery_candidate(ip, manufacturer, source="bulk_add")
```

### Run discovery scan
```python
service = DiscoveryService()
manufacturer = Manufacturer.objects.get(code='shure')

# Full discovery (includes CIDRs and FQDNs)
service.run_manufacturer_discovery(
    manufacturer,
    scan_cidrs=True,
    scan_fqdns=True,
    max_hosts=1024
)
```

### Get discovery candidates
```python
service = DiscoveryService()

# Get all candidate IPs for a manufacturer
candidates = service.get_discovery_candidates(
    'shure',
    scan_cidrs=False,
    scan_fqdns=False
)

print(f"Found {len(candidates)} candidate IPs:")
for ip in candidates:
    print(f"  - {ip}")
```

### Remove IPs from discovery
```python
service = DiscoveryService()
manufacturer = Manufacturer.objects.get(code='shure')

service.remove_discovery_candidate("172.21.1.100", manufacturer)
```

## Management Commands

### Using services in commands

```python
from django.core.management.base import BaseCommand
from micboard.models import Manufacturer
from micboard.services import DeviceService

class Command(BaseCommand):
    def handle(self, *args, **options):
        for manufacturer in Manufacturer.objects.filter(is_active=True):
            service = DeviceService(manufacturer)
            created, updated = service.sync_devices_from_api()
            self.stdout.write(
                self.style.SUCCESS(
                    f"{manufacturer.name}: {created} created, {updated} updated"
                )
            )
```

## API Views

### Using services in views

```python
from rest_framework.views import APIView
from rest_framework.response import Response
from micboard.services import DeviceService, PollingService

class DeviceListView(APIView):
    def get(self, request, manufacturer_code):
        manufacturer = get_object_or_404(Manufacturer, code=manufacturer_code)
        service = DeviceService(manufacturer)
        devices = service.get_active_devices()
        serializer = DeviceSerializer(devices, many=True)
        return Response(serializer.data)

class PollingHealthView(APIView):
    def get(self, request):
        service = PollingService()
        health = service.get_polling_health()
        return Response(health)

class TriggerPollView(APIView):
    def post(self, request, manufacturer_code):
        manufacturer = get_object_or_404(Manufacturer, code=manufacturer_code)
        service = PollingService()
        result = service.poll_manufacturer(manufacturer)
        return Response(result)
```

## Background Tasks

### Using services in tasks

```python
# tasks.py
from micboard.services import PollingService
from micboard.models import Manufacturer

def poll_all_task():
    """Celery/Django-Q task"""
    service = PollingService()
    return service.poll_all_manufacturers()

def poll_manufacturer_task(manufacturer_id):
    """Celery/Django-Q task"""
    manufacturer = Manufacturer.objects.get(pk=manufacturer_id)
    service = PollingService()
    return service.poll_manufacturer(manufacturer)
```

## Testing

### Mock services for testing

```python
import pytest
from unittest.mock import Mock
from micboard.services import DeviceService

def test_device_sync(mocker, shure_manufacturer):
    # Mock the client
    mock_client = Mock()
    mock_client.get_devices.return_value = [
        {
            "id": "device-123",
            "model": "ULXD4Q",
            "ipAddress": "172.21.1.100",
            "name": "Test Device"
        }
    ]
    
    # Test service with mocked client
    service = DeviceService(shure_manufacturer, client=mock_client)
    created, updated = service.sync_devices_from_api()
    
    assert created == 1
    assert updated == 0
    mock_client.get_devices.assert_called_once()
```

### Integration testing

```python
def test_polling_integration(shure_manufacturer):
    """Test with real API (integration test)"""
    service = PollingService()
    result = service.poll_manufacturer(shure_manufacturer)
    
    assert 'devices_created' in result
    assert 'devices_updated' in result
    assert isinstance(result['errors'], list)
```

## Debugging

### Enable debug logging

```python
import logging

# Enable service logging
logging.getLogger('micboard.services').setLevel(logging.DEBUG)

# Enable integration client logging
logging.getLogger('micboard.integrations').setLevel(logging.DEBUG)
```

### Check service internals

```python
from micboard.services import DeviceService

service = DeviceService(manufacturer)

# Check client type
print(f"Client: {type(service.client)}")
print(f"Plugin: {type(service.plugin)}")

# Check manufacturer config
print(f"Manufacturer: {service.manufacturer.name}")
print(f"API URL: {service.client.base_url}")
```

## Common Patterns

### Error handling
```python
from micboard.services import DeviceService

try:
    service = DeviceService(manufacturer)
    result = service.poll_and_sync_all()
    
    if result['errors']:
        logger.warning(f"Errors during polling: {result['errors']}")
    else:
        logger.info(f"Polling successful: {result}")
except Exception as e:
    logger.exception(f"Polling failed: {e}")
```

### Batch operations
```python
from micboard.services import DeviceService
from micboard.models import Manufacturer

# Process all manufacturers
for manufacturer in Manufacturer.objects.filter(is_active=True):
    try:
        service = DeviceService(manufacturer)
        created, updated = service.sync_devices_from_api()
        print(f"{manufacturer.name}: {created} created, {updated} updated")
    except Exception as e:
        print(f"{manufacturer.name}: ERROR - {e}")
```

### Conditional polling
```python
from micboard.services import PollingService

service = PollingService()

# Only poll healthy manufacturers
health = service.get_polling_health()
for code, mfr_health in health['manufacturers'].items():
    if mfr_health['api_status'] == 'healthy':
        manufacturer = Manufacturer.objects.get(code=code)
        service.poll_manufacturer(manufacturer)
```

## See Also

- [Services Architecture Guide](services.md)
- [Shure System API Endpoints](shure-system-api-endpoints.md)
- [Refactoring Summary](SERVICES_REFACTORING_SUMMARY.md)
