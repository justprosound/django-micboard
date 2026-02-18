# API Reference

Complete API documentation for Django Micboard.

## REST API Endpoints

### Device Data

#### GET /api/data.json

Returns complete device data including receivers, channels, transmitters, and configuration.

**Response:**
```json
{
  "receivers": [
    {
      "id": 1,
      "name": "ULX-D Receiver 1",
      "device_type": "ulxd",
      "ip": "192.168.1.100",
      "channels": [
        {
          "channel": 1,
          "transmitter": {
            "slot": 1,
            "battery": 75,
            "audio_level": -10,
            "rf_level": -50,
            "frequency": "540.000",
            "name": "Wireless Mic 1"
          }
        }
      ]
    }
  ],
  "discovered": [...],
  "config": {...},
  "groups": [...]
}
```

**Rate Limit:** 120 requests per 60 seconds (2 req/sec)

#### GET /api/receivers/

List all receivers with summary information.

**Response:**
```json
[
  {
    "id": 1,
    "name": "ULX-D Receiver 1",
    "device_type": "ulxd",
    "ip": "192.168.1.100",
    "is_active": true,
    "last_seen": "2025-10-15T10:30:00Z"
  }
]
```

#### GET /api/receivers/{id}/

Get detailed information for a specific receiver.

**Response:**
```json
{
  "id": 1,
  "name": "ULX-D Receiver 1",
  "device_type": "ulxd",
  "ip": "192.168.1.100",
  "channels": [...],
  "battery_health": "good",
  "signal_quality": "excellent"
}
```

### Health & Status

#### GET /api/health/

Check API and Shure System API health status.

**Response:**
```json
{
  "status": "healthy",
  "shure_api": {
    "status": "healthy",
    "base_url": "http://192.168.1.50:10000",
    "consecutive_failures": 0
  },
  "timestamp": "2025-10-15T10:30:00Z"
}
```

### Device Discovery

#### POST /api/discover/

Discover new Shure devices on the network.

**Request Body:**
```json
{
  "scan_subnet": "192.168.1.0/24"
}
```

**Response:**
```json
{
  "discovered": 3,
  "devices": [
    {
      "ip": "192.168.1.100",
      "device_type": "ulxd",
      "channels": 2
    }
  ]
}
```

#### POST /api/refresh/

Force refresh device data from Shure System API.

**Response:**
```json
{
  "status": "success",
  "receivers_updated": 5,
  "timestamp": "2025-10-15T10:30:00Z"
}
```

### Configuration

#### GET /api/config/

Get current configuration settings.

**Response:**
```json
{
  "polling_interval": 5000,
  "alert_battery_threshold": 20,
  "enable_websocket": true
}
```

#### POST /api/config/

Update configuration settings.

**Request Body:**
```json
{
  "key": "polling_interval",
  "value": "3000"
}
```

### Groups

#### PUT /api/groups/{id}/

Update group configuration.

**Request Body:**
```json
{
  "title": "Main Stage",
  "slots": [1, 2, 3, 4],
  "hide_charts": false
}
```

## WebSocket API

### Connection

Connect to WebSocket for real-time updates:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/micboard/');

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Received update:', data);
};
```

### Message Types

#### Device Update
```json
{
  "type": "device_update",
  "receiver_id": 1,
  "data": {
    "channels": [...]
  }
}
```

#### Alert
```json
{
  "type": "alert",
  "severity": "warning",
  "message": "Low battery on Wireless Mic 1",
  "channel_id": 5
}
```

#### Status
```json
{
  "type": "status",
  "message": "Connected to Shure System API"
}
```

## Python API

### Models

#### WirelessChassis

```python
from micboard.models import WirelessChassis

# Get all active chassis
chassis = WirelessChassis.objects.filter(status='online')

# Get chassis by manufacturer
shure_chassis = WirelessChassis.objects.filter(manufacturer__code='shure')

# Get with related units
chassis = WirelessChassis.objects.prefetch_related('wireless_units').get(id=1)
```

#### WirelessUnit

```python
from micboard.models import WirelessUnit

# Get units with battery status
units = WirelessUnit.objects.filter(battery_percentage__lt=20)

# Get units for a chassis
units = WirelessUnit.objects.filter(base_chassis=chassis)

# Get by device type
transmitters = WirelessUnit.objects.filter(device_type='mic_transmitter')
```

#### PerformerAssignment

```python
from micboard.models import PerformerAssignment

# Get active assignments
assignments = PerformerAssignment.objects.filter(is_active=True)

# Get assignments by performer
performer_assignments = PerformerAssignment.objects.filter(performer=performer)

# Get assignments for a wireless unit
unit_assignments = PerformerAssignment.objects.filter(wireless_unit=unit)
```

### Shure API Client

```python
from micboard.integrations.shure.client import ShureSystemAPIClient

# Initialize client
client = ShureSystemAPIClient()

# Get all devices
devices = client.get_devices()

# Get specific device
device = client.get_device('device-id-123')

# Poll all devices
data = client.poll_all_devices()

# Check health
health = client.check_health()
```

### Services

```python
from micboard.services.core.hardware import HardwareService

# Get normalized hardware data
hardware = HardwareService.get_hardware_by_manufacturer(manufacturer_code='shure')

# Sync hardware from API
result = HardwareService.sync_from_api(manufacturer=manufacturer)
```

### Decorators

```python
from micboard.decorators import rate_limit_view

@rate_limit_view(max_requests=60, window_seconds=60)
def my_api_view(request):
    return JsonResponse({'status': 'ok'})
```

## Management Commands

### poll_devices

Continuously poll devices and broadcast updates:

```bash
python manage.py poll_devices --interval 5
```

**Options:**
- `--interval` - Polling interval in seconds (default: 5)
- `--once` - Poll once and exit

### check_api_health

Check Shure System API health:

```bash
python manage.py check_api_health
```

## Rate Limiting

All API endpoints have built-in rate limiting:

- Default: 120 requests per 60 seconds
- Per-endpoint customization available
- Token bucket algorithm
- Django cache-based

See [Rate Limiting Guide](rate-limiting.md) for details.

## Error Responses

### Standard Error Format

```json
{
  "error": "Error message",
  "status": 400,
  "details": "Optional detailed information"
}
```

### Common Status Codes

- `200` - Success
- `400` - Bad Request
- `404` - Not Found
- `429` - Rate Limit Exceeded
- `500` - Internal Server Error
- `503` - Service Unavailable

## Pagination

List endpoints support pagination via query parameters:

```
GET /api/receivers/?page=2&page_size=50
```

**Parameters:**
- `page` - Page number (default: 1)
- `page_size` - Items per page (default: 100, max: 1000)

**Response:**
```json
{
  "count": 250,
  "next": "/api/receivers/?page=3",
  "previous": "/api/receivers/?page=1",
  "results": [...]
}
```
