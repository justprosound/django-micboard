# Services Layer Architecture

## Overview

The services module provides a clean separation between business logic and infrastructure concerns (HTTP clients, database models, tasks).

## Design Principles

### Single Responsibility
Each service handles one specific domain:
- **DeviceService**: Device lifecycle management (CRUD, state)
- **DiscoveryService**: Network discovery and IP management
- **PollingService**: Orchestration of polling tasks
- **TransmitterService**: Transmitter-specific operations
- **ChargerService**: Charger and charging slot management

### Dependency Injection
Services receive dependencies via constructor, enabling testing:

```python
class DeviceService:
    def __init__(self, manufacturer: Manufacturer, client: BaseAPIClient | None = None):
        self.manufacturer = manufacturer
        self.client = client or self._get_default_client()
```

### Thin Clients, Fat Services
Integration clients (Shure, Sennheiser) are thin HTTP wrappers.
Business logic lives in services:

```python
# ❌ BAD: Business logic in client
class ShureDeviceClient:
    def poll_all_devices(self):
        devices = self.get_devices()
        for device in devices:
            # Transform, validate, save to database...

# ✅ GOOD: Client is HTTP-only
class ShureDeviceClient:
    def get_devices(self) -> list[dict]:
        return self.api_client._make_request("GET", "/api/v1/devices")

# ✅ Service handles business logic
class DeviceService:
    def sync_devices_from_api(self):
        devices = self.client.devices.get_devices()
        for device in devices:
            self._transform_and_save(device)
```

## Service Directory Structure

```
micboard/services/
├── __init__.py              # Export public service APIs
├── device_service.py        # Device management
├── discovery_service.py     # Discovery (moved from micboard/discovery/)
├── polling_service.py       # Polling orchestration
├── transmitter_service.py   # Transmitter operations
├── charger_service.py       # Charger management
├── alert_service.py         # Alert generation and management
├── email.py                 # Email notifications (existing)
└── alerts.py                # Alert utilities (existing)
```

## Service APIs

### Device Service

Manages device lifecycle across all manufacturers.

```python
from micboard.services import DeviceService

# Initialize with manufacturer
service = DeviceService(manufacturer=shure_manufacturer)

# Sync devices from manufacturer API
devices_created, devices_updated = service.sync_devices_from_api()

# Get active devices
devices = service.get_active_devices()

# Update device state
service.update_device_state(device_id, {"is_online": True})

# Mark device offline
service.mark_offline(device_id)
```

**Methods**:
- `sync_devices_from_api()` - Pull devices from API, create/update models
- `get_active_devices()` - Query active devices for this manufacturer
- `get_device_by_api_id(api_device_id)` - Lookup by manufacturer device ID
- `update_device_state(device_id, state)` - Update device attributes
- `mark_online(device_id)` - Set device online
- `mark_offline(device_id)` - Set device offline
- `enrich_device_data(device_id)` - Fetch additional metadata from API

### Discovery Service

Manages network discovery and IP address tracking.

**Moved from `micboard/discovery/service.py` to `micboard/services/discovery_service.py`**

```python
from micboard.services import DiscoveryService

service = DiscoveryService()

# Add IP to manufacturer's discovery list
service.add_discovery_candidate("172.21.1.100", manufacturer, source="manual")

# Remove IP from discovery list
service.remove_discovery_candidate("172.21.1.100", manufacturer)

# Run full discovery for manufacturer
service.run_manufacturer_discovery(manufacturer, scan_cidrs=True, scan_fqdns=True)

# Get all candidate IPs (from Receivers, DiscoveredDevices, CIDRs, FQDNs)
candidates = service.get_discovery_candidates("shure", scan_cidrs=True)
```

**Methods**:
- `add_discovery_candidate(ip, manufacturer, source)` - Add IP to discovery
- `remove_discovery_candidate(ip, manufacturer)` - Remove IP from discovery
- `run_manufacturer_discovery(manufacturer, **options)` - Full discovery scan
- `get_discovery_candidates(code, **options)` - Get candidate IP list
- `sync_discovery_to_api(manufacturer)` - Push Django IPs to manufacturer API

### Polling Service

Orchestrates polling tasks across all manufacturers.

```python
from micboard.services import PollingService

service = PollingService()

# Poll all manufacturers
results = service.poll_all_manufacturers()

# Poll specific manufacturer
result = service.poll_manufacturer(manufacturer)

# Get polling health status
health = service.get_polling_health()
```

**Methods**:
- `poll_all_manufacturers()` - Poll every active manufacturer
- `poll_manufacturer(manufacturer)` - Poll single manufacturer
- `get_polling_health()` - Check if polling is healthy
- `broadcast_device_updates(manufacturer, data)` - Send WebSocket updates

### Transmitter Service

Handles transmitter-specific operations.

```python
from micboard.services import TransmitterService

service = TransmitterService(manufacturer)

# Get transmitter data from API
tx_data = service.get_transmitter_data(device_id, channel)

# Update transmitter model
service.update_transmitter(transmitter_id, tx_data)

# Check battery status
battery_low = service.check_battery_alert(transmitter_id)
```

**Methods**:
- `get_transmitter_data(device_id, channel)` - Fetch from API
- `update_transmitter(tx_id, data)` - Update Django model
- `check_battery_alert(tx_id)` - Battery threshold check
- `get_transmitters_for_device(device_id)` - Get all transmitters

### Charger Service

Manages charger and charging slot operations.

```python
from micboard.services import ChargerService

service = ChargerService(manufacturer)

# Sync chargers from API
service.sync_chargers_from_api()

# Get charger status
status = service.get_charger_status(charger_id)

# Update slot charging status
service.update_slot_status(slot_id, charging=True, battery=75)
```

**Methods**:
- `sync_chargers_from_api()` - Pull charger data
- `get_charger_status(charger_id)` - Get charger state
- `update_slot_status(slot_id, **data)` - Update charging slot
- `get_available_slots(charger_id)` - Find empty slots

## Usage in Tasks

Tasks should be thin orchestrators that call services:

```python
# ❌ BAD: Task contains business logic
def poll_manufacturer_devices(manufacturer_id):
    manufacturer = Manufacturer.objects.get(pk=manufacturer_id)
    plugin = get_manufacturer_plugin(manufacturer.code)
    client = plugin.get_client()
    devices = client.get_devices()
    for device in devices:
        # Complex transformation and saving logic...

# ✅ GOOD: Task delegates to service
def poll_manufacturer_devices(manufacturer_id):
    manufacturer = Manufacturer.objects.get(pk=manufacturer_id)
    service = PollingService()
    return service.poll_manufacturer(manufacturer)
```

## Usage in API Views

Views should call services, not clients directly:

```python
# ❌ BAD: View calls client directly
def device_list_view(request):
    manufacturer = get_object_or_404(Manufacturer, code='shure')
    plugin = get_manufacturer_plugin('shure')
    client = plugin.get_client()
    devices = client.get_devices()
    # Transform and serialize...

# ✅ GOOD: View uses service
def device_list_view(request):
    manufacturer = get_object_or_404(Manufacturer, code='shure')
    service = DeviceService(manufacturer)
    devices = service.get_active_devices()
    return DeviceListSerializer(devices, many=True).data
```

## Testing Services

Services are easier to test than clients:

```python
import pytest
from micboard.services import DeviceService

def test_sync_devices(mock_client, shure_manufacturer):
    # Mock the client
    mock_client.devices.get_devices.return_value = [
        {"id": "dev1", "model": "ULXD4Q", "ipAddress": "172.21.1.100"}
    ]

    # Test service
    service = DeviceService(shure_manufacturer, client=mock_client)
    created, updated = service.sync_devices_from_api()

    assert created == 1
    assert updated == 0
```

## Migration Strategy

1. **Create services** with new clean APIs
2. **Update tasks** to call services instead of clients
3. **Update views** to call services
4. **Refactor clients** to remove business logic (HTTP-only)
5. **Deprecate old patterns** via warnings
6. **Remove deprecated code** in next major version

## Benefits

- **Testability**: Mock services easily, no HTTP mocking needed
- **Reusability**: Same service used by tasks, views, management commands
- **Maintainability**: Business logic in one place
- **Flexibility**: Swap implementations without changing callers
- **Documentation**: Services are self-documenting interfaces

## Anti-Patterns to Avoid

### ❌ God Services
Don't create `ManufacturerService` that does everything.
Split into focused services.

### ❌ Anemic Services
Don't create pass-through services with no logic:
```python
class DeviceService:
    def get_devices(self):
        return self.client.get_devices()  # No value added
```

### ❌ Circular Dependencies
Services should not depend on each other in cycles.
Use dependency injection and events/signals instead.

### ❌ Direct Model Access in Clients
Clients should not import Django models:
```python
# ❌ BAD
class ShureDeviceClient:
    def save_device(self, device_data):
        Receiver.objects.create(...)  # Client should not know about models
```

## See Also

- [API Documentation](api-reference.md)
- [Plugin Development](plugin-development.md)
- [Architecture Overview](architecture.md)
