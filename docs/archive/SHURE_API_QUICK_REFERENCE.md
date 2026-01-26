# Shure API Integration - Quick Reference

> **Status:** ✅ Validated and working (2026-01-22)

## Quick Start

### 1. Check API Health
```python
from micboard.integrations.shure.client import ShureSystemAPIClient

client = ShureSystemAPIClient()
health = client.check_health()
print(health)  # {'status': 'healthy'}
```

### 2. Manage Discovery IPs
```python
# Get current IPs
ips = client.get_discovery_ips()
print(f"Configured: {len(ips)} IPs")

# Add new IPs
client.add_discovery_ips(['192.168.1.100', '192.168.1.101'])

# Remove IPs
client.remove_discovery_ips(['192.168.1.100'])
```

### 3. Get Devices
```python
# Get all discovered devices
devices = client.get_devices()
for device in devices:
    print(f"{device['model']} at {device['ip_address']}")
```

### 4. Use Plugin Interface
```python
from micboard.integrations.shure.plugin import ShurePlugin
from micboard.models import Manufacturer

manufacturer = Manufacturer.objects.get(code='shure')
plugin = ShurePlugin(manufacturer)

# Get devices (transformed to micboard format)
devices = plugin.get_devices()

# Check health
health = plugin.check_health()

# Get device details
identity = plugin.get_device_identity(device_id)
network = plugin.get_device_network(device_id)
status = plugin.get_device_status(device_id)
```

### 5. Sync to Django Models
```bash
# Manual polling
python manage.py poll_devices --manufacturer shure

# Async polling
python manage.py poll_devices --manufacturer shure --async
```

```python
# Programmatic polling
from micboard.services import PollingService

service = PollingService()
result = service.poll_manufacturer(manufacturer)
print(f"Created: {result['devices_created']}")
print(f"Updated: {result['devices_updated']}")
```

### 6. WebSocket Bi-Directional Sync
```python
# Get WebSocket URL
ws_url = plugin.get_client().websocket_url
print(ws_url)  # wss://localhost:10000/api/v1/subscriptions/websocket/create

# Connect and subscribe (in async context)
def on_message(message):
    print(f"Device update: {message}")

plugin.connect_and_subscribe(on_message=on_message)
```

## Configuration

### Environment Variables
```bash
# Required
MICBOARD_SHURE_API_BASE_URL=https://localhost:10000
MICBOARD_SHURE_API_SHARED_KEY=your-256-character-key

# Optional
MICBOARD_SHURE_API_VERIFY_SSL=false  # Set true for production
MICBOARD_SHURE_API_TIMEOUT=10
```

### Django Settings
```python
# demo/settings.py
MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": os.environ.get("MICBOARD_SHURE_API_BASE_URL"),
    "SHURE_API_SHARED_KEY": os.environ.get("MICBOARD_SHURE_API_SHARED_KEY"),
    "SHURE_API_VERIFY_SSL": os.environ.get("MICBOARD_SHURE_API_VERIFY_SSL", "true").lower() == "true",
}
```

## API Endpoints

### Device Operations
```python
# List all devices
GET /api/v1/devices

# Get device details
GET /api/v1/devices/{device_id}

# Get device channels
GET /api/v1/devices/{device_id}/channels

# Get device identity
GET /api/v1/devices/{device_id}/identity

# Get device network
GET /api/v1/devices/{device_id}/network

# Get device status
GET /api/v1/devices/{device_id}/status

# Get transmitter data
GET /api/v1/devices/{device_id}/tx/{channel_number}
```

### Discovery Management
```python
# Get discovery IPs
GET /api/v1/config/discovery/ips

# Set discovery IPs
PUT /api/v1/config/discovery/ips
Body: {"ips": ["192.168.1.100", "192.168.1.101"]}

# Remove discovery IPs
PATCH /api/v1/config/discovery/ips/remove
Body: {"ips": ["192.168.1.100"]}
```

### WebSocket
```python
# Connect to WebSocket
WSS /api/v1/subscriptions/websocket/create
```

## Data Flow

### Device → Django (Polling)
```
1. poll_devices command runs
2. ShurePlugin.get_devices() fetches from API
3. PollingService updates Django models
4. Django signals broadcast changes
5. Django Channels pushes to UI
```

### Device → Django (Real-time)
```
1. Device state changes (battery, RF, etc.)
2. Shure System API sends WebSocket event
3. Django receives and processes event
4. Models updated
5. Django Channels broadcasts to UI
```

### Django → Device (Control)
```
1. User action in UI
2. Django view/API endpoint
3. ShurePlugin method call
4. Shure System API PUT/POST
5. Device updates
6. WebSocket event confirms change
```

## Common Tasks

### Add Devices to Discovery
```python
from micboard.integrations.shure.client import ShureSystemAPIClient

client = ShureSystemAPIClient()

# Add IP range
ips = [f"192.168.1.{i}" for i in range(100, 111)]
client.add_discovery_ips(ips)

# Verify
print(f"Total IPs: {len(client.get_discovery_ips())}")
```

### Poll and Sync Devices
```python
from micboard.services import PollingService
from micboard.models import Manufacturer, Receiver

manufacturer = Manufacturer.objects.get(code='shure')

# Poll
service = PollingService()
result = service.poll_manufacturer(manufacturer)

# Check results
receivers = Receiver.objects.filter(manufacturer=manufacturer)
print(f"Receivers: {receivers.count()}")
for receiver in receivers:
    print(f"  - {receiver.name} ({receiver.ip})")
```

### Monitor Device State
```python
from micboard.models import Receiver, Channel, Transmitter

# Get all Shure receivers
receivers = Receiver.objects.filter(manufacturer__code='shure')

for receiver in receivers:
    print(f"\n{receiver.name} ({receiver.status})")

    # Get channels
    for channel in receiver.channels.all():
        print(f"  Channel {channel.channel_number}")

        # Get transmitter
        try:
            tx = channel.transmitter
            print(f"    Battery: {tx.battery}%")
            print(f"    RF Level: {tx.rf_level} dB")
            print(f"    Audio Level: {tx.audio_level} dB")
        except Transmitter.DoesNotExist:
            print("    No transmitter")
```

### Test WebSocket Connection
```python
import asyncio
from micboard.integrations.shure.plugin import ShurePlugin
from micboard.models import Manufacturer

async def test_websocket():
    manufacturer = Manufacturer.objects.get(code='shure')
    plugin = ShurePlugin(manufacturer)

    def on_message(message):
        print(f"Received: {message}")

    # Connect (this is a blocking call)
    await plugin.connect_and_subscribe(on_message=on_message)

# Run
asyncio.run(test_websocket())
```

## Validation

### Quick Health Check
```bash
# Load environment
source .env.local && export $(grep -v '^#' .env.local | xargs)

# Run validation
PYTHONPATH=$PWD uv run python scripts/validate_shure_integration.py
```

### Run Tests
```bash
# All Shure tests
.venv/bin/pytest micboard/tests/test_shure*.py -v

# Specific test file
.venv/bin/pytest micboard/tests/test_shure_client.py -v

# All tests
.venv/bin/pytest micboard/tests/ -v
```

## Troubleshooting

### No Devices Found
```python
# Check discovery IPs
client = ShureSystemAPIClient()
ips = client.get_discovery_ips()
print(f"Discovery IPs: {len(ips)}")

# Check API health
health = client.check_health()
print(f"API Status: {health['status']}")

# Wait for discovery (can take 30-60 seconds)
import time
time.sleep(30)
devices = client.get_devices()
print(f"Devices found: {len(devices)}")
```

### Authentication Error
```python
# Verify shared key is set
from django.conf import settings
config = settings.MICBOARD_CONFIG
print("Shared key configured:", bool(config.get('SHURE_API_SHARED_KEY')))
```

### WebSocket Connection Issues
```python
# Check WebSocket URL
client = ShureSystemAPIClient()
print(f"WebSocket URL: {client.websocket_url}")

# Verify SSL settings
from django.conf import settings
print(f"SSL Verify: {settings.MICBOARD_CONFIG.get('SHURE_API_VERIFY_SSL')}")
```

### Polling Not Working
```bash
# Check Django-Q cluster is running
python manage.py qcluster

# Run manual poll with verbose output
python manage.py poll_devices --manufacturer shure

# Check logs
tail -f /var/log/micboard/polling.log
```

## Supported Devices

### Shure ULXD Series
- **ULXD4D** - Dual-channel digital receiver
- **ULXD4Q** - Quad-channel digital receiver
- **QLXD4** - Single-channel digital receiver
- **AD4D** - Dual-channel Axient Digital receiver

### Transmitter Types
- Handheld
- Bodypack
- Plug-on

## File Locations

```
micboard/
├── integrations/
│   └── shure/
│       ├── client.py              # Main API client
│       ├── device_client.py       # Device operations
│       ├── discovery_client.py    # Discovery management
│       ├── plugin.py              # Plugin interface
│       ├── transformers.py        # Data transformation
│       ├── rate_limiter.py        # Rate limiting
│       ├── exceptions.py          # Shure-specific exceptions
│       └── utils.py               # Utility functions
├── services/
│   └── polling.py                 # PollingService
├── tasks/
│   ├── polling_tasks.py           # Background polling
│   └── websocket_tasks.py         # WebSocket subscriptions
├── signals/
│   └── broadcast_signals.py       # Event broadcasting
└── tests/
    ├── test_shure_client.py       # Client tests
    ├── test_shure_device_client.py# Device tests
    └── test_shure_transformers.py # Transform tests

scripts/
└── validate_shure_integration.py  # Validation script

docs/
├── SHURE_BIDIRECTIONAL_SYNC_VALIDATION.md  # Full report
├── SHURE_INTEGRATION_SESSION_SUMMARY.md    # Session summary
└── SHURE_API_QUICK_REFERENCE.md            # This file
```

## Resources

- **Full Documentation:** [SHURE_BIDIRECTIONAL_SYNC_VALIDATION.md](SHURE_BIDIRECTIONAL_SYNC_VALIDATION.md)
- **Session Summary:** [SHURE_INTEGRATION_SESSION_SUMMARY.md](SHURE_INTEGRATION_SESSION_SUMMARY.md)
- **Validation Script:** [validate_shure_integration.py](../scripts/validate_shure_integration.py)
- **Shure System API Docs:** https://pubs.shure.com/guide/SystemOn/en-US
- **Architecture:** [architecture.md](architecture.md)
- **Plugin Development:** [plugin-development.md](plugin-development.md)

---

**Last Updated:** 2026-01-22
**Status:** ✅ Validated and production-ready
