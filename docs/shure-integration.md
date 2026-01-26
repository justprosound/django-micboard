# Shure System API Integration

Complete guide to integrating django-micboard with Shure wireless microphone systems.

## Overview

Django Micboard integrates with Shure's System API to provide comprehensive monitoring of wireless microphone systems including:

- **ULX-D Series** - Digital wireless systems
- **QLX-D Series** - Digital wireless with advanced features
- **UHF-R Series** - Professional wireless systems
- **Axient Digital (AD)** - High-end digital wireless
- **PSM Series** - Personal monitoring systems

## System Requirements

### Hardware Requirements

- Shure wireless microphone system with System API support
- Network connectivity (Ethernet recommended)
- System administrator access

### Software Requirements

- Shure System API enabled and configured
- HTTPS access (self-signed certificates acceptable)
- Network access from Django application server

## API Configuration

### Enable System API

1. **Access System Interface**
   - Connect to your Shure system's web interface
   - Log in with administrator credentials

2. **Navigate to API Settings**
   - Go to **Network → API Settings**
   - Enable **"System API"**
   - Configure authentication method

3. **Configure Authentication**
   - Choose authentication type (HTTP Digest recommended)
   - Set username and password
   - Note the API base URL and port

### Django Configuration

Add to your `settings.py`:

```python
# Shure System API Configuration
MICBOARD_SHURE_API = {
    'BASE_URL': 'https://your-shure-system.local:443',
    'USERNAME': 'api_user',
    'PASSWORD': 'your_secure_password',
    'VERIFY_SSL': True,  # Set False for self-signed certificates
    'TIMEOUT': 30,       # Request timeout in seconds
}
```

## Device Discovery

### Automatic Discovery

Configure IP ranges for device discovery:

```bash
# Add discovery IP ranges
python manage.py add_shure_devices --cidr 192.168.1.0/24

# Add specific IPs
python manage.py add_shure_devices --ips 192.168.1.100 192.168.1.101
```

### Manual Device Addition

Add devices directly via admin interface:

1. Go to `/admin/micboard/device/`
2. Click "Add Device"
3. Enter device details:
   - Manufacturer: Shure
   - Device ID (from Shure system)
   - IP Address
   - Model information

## Device Monitoring

### Real-time Data

Django Micboard monitors:

- **Battery Levels** - Percentage and charging status
- **RF Signal Strength** - dBm values and quality indicators
- **Audio Levels** - Input/output meters and peak detection
- **Device Status** - Online/offline state
- **Channel Information** - Frequency, bandwidth, encryption

### WebSocket Updates

Real-time updates via WebSocket:

```javascript
// Connect to WebSocket
const ws = new WebSocket('ws://your-server/ws/devices/');

// Listen for updates
ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Device update:', data);
};
```

## Management Commands

### Device Polling

```bash
# Poll all Shure devices once
python manage.py poll_devices --manufacturer shure

# Continuous polling (recommended for production)
python manage.py poll_devices --manufacturer shure --continuous --interval 30

# Dry run to test connectivity
python manage.py poll_devices --manufacturer shure --dry-run
```

### Connection Health

```bash
# Check connection status
python manage.py check_connections --manufacturer shure

# Monitor with alerts
python manage.py check_connections --manufacturer shure --alert
```

## API Endpoints

### Device Information

```python
from micboard.integrations.shure.client import ShureSystemAPIClient

client = ShureSystemAPIClient()

# Get all devices
devices = client.get_devices()

# Get specific device
device = client.get_device('device_id')

# Get device status
status = client.get_device_status('device_id')
```

### Discovery Management

```python
# Get discovery IPs
ips = client.get_discovery_ips()

# Add discovery IPs
client.add_discovery_ips(['192.168.1.100', '192.168.1.101'])

# Remove discovery IPs
client.remove_discovery_ips(['192.168.1.100'])
```

## Troubleshooting

### Connection Issues

**API Connection Failed:**
- Verify BASE_URL in settings
- Check username/password credentials
- Ensure Shure system is accessible on network
- Check SSL certificate settings

**Device Not Found:**
- Confirm device is powered on and connected
- Verify IP address is in discovery range
- Check Shure system device list
- Review network firewall settings

### Data Issues

**Stale Data:**
- Check polling interval settings
- Verify WebSocket connections
- Monitor connection health logs

**Missing Metrics:**
- Confirm device firmware version
- Check API permissions
- Review Shure system configuration

### Performance Issues

**Slow Updates:**
- Reduce polling interval if needed
- Check network latency
- Monitor Django server resources
- Consider Redis caching for WebSocket

## Advanced Configuration

### Custom Device Types

Support additional Shure device types by extending the plugin:

```python
from micboard.manufacturers.base import BaseManufacturerPlugin

class CustomShurePlugin(BaseManufacturerPlugin):
    def get_devices(self):
        # Custom device discovery logic
        pass

    def get_device_status(self, device_id):
        # Custom status retrieval
        pass
```

### API Rate Limiting

Configure rate limiting for API calls:

```python
MICBOARD_RATE_LIMITS = {
    'shure_api_calls': '100/minute',
    'device_polling': '10/minute',
}
```

### Logging Configuration

Enable detailed Shure API logging:

```python
LOGGING = {
    'loggers': {
        'micboard.integrations.shure': {
            'level': 'DEBUG',
            'handlers': ['console'],
        },
    },
}
```

## Security Considerations

- Use HTTPS for API communication
- Store credentials securely (environment variables recommended)
- Implement proper firewall rules
- Regular credential rotation
- Monitor API access logs

## Support Resources

- [Shure System API Documentation](https://shure.secure.force.com/apiexplorer)
- [Django Micboard GitHub Issues](https://github.com/justprosound/django-micboard/issues)
- [Shure Support](https://www.shure.com/en-US/support)

4. **Network Configuration**
   - Ensure device has static IP or DHCP reservation
   - Configure firewall rules if needed
   - Test connectivity from Django server

## Authentication

### HTTP Digest Authentication

Shure System API uses HTTP Digest Authentication with a shared key.

**Authentication Requirements:**
- **Method:** HTTP Digest Authentication (RFC 7616)
- **Shared Key:** Configured at system level
- **Headers:** Include `X-Shure-Auth-Key` for enhanced security

### Implementation in Python/Requests

```python
from requests.auth import HTTPDigestAuth

# Configure authentication
auth = HTTPDigestAuth(username="shure", password="shared_key")

# Make authenticated request
response = requests.get(
    "https://192.168.1.100:2420/api/v1/devices",
    auth=auth,
    verify=False  # For self-signed certificates
)
```

### Django Implementation

In micboard's Shure integration:

```python
from requests.auth import HTTPDigestAuth

class ShureSystemAPIClient(BaseHTTPClient):
    def __init__(
        self,
        api_base_url: str,
        shared_key: str,
        *,
        ssl_verify: bool = True,
        timeout: int = 10
    ):
        """
        Initialize Shure System API client.

        Args:
            api_base_url: Base URL of Shure system (e.g., https://192.168.1.100:2420)
            shared_key: Shared authentication key from system settings
            ssl_verify: Whether to verify SSL certificates (default: True)
            timeout: Request timeout in seconds (default: 10)
        """
        self.api_base_url = api_base_url
        self.shared_key = shared_key
        self.ssl_verify = ssl_verify
        self.timeout = timeout
        self.auth = HTTPDigestAuth("shure", shared_key)

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make authenticated request to Shure system."""
        url = f"{self.api_base_url}{endpoint}"
        response = requests.request(
            method,
            url,
            auth=self.auth,
            verify=self.ssl_verify,
            timeout=self.timeout,
            **kwargs
        )
        return response.json()
```

## API Endpoints

### Core Endpoints

#### Devices List
```
GET /api/v1/devices
```
Returns all devices connected to the Shure system.

**Response:**
```json
{
  "devices": [
    {
      "device_id": "device-uuid",
      "device_name": "Handheld 1",
      "device_type": "Transmitter",
      "model": "ULXD2",
      "status": "online",
      "battery_percentage": 85,
      "rf_level": -50
    }
  ]
}
```

#### Device Details
```
GET /api/v1/devices/{device_id}
```
Returns detailed information about a specific device.

#### Device Channels
```
GET /api/v1/devices/{device_id}/channels
```
Returns channel configuration and status for a device.

#### Transmitter Data
```
GET /api/v1/devices/{device_id}/transmitter
```
Returns transmitter-specific data (battery, RF level, frequency, etc.).

### WebSocket Connection

**WebSocket URL:**
```
wss://{api_host}:{port}/api/v1/ws
```

**Purpose:** Real-time device status updates and events

**Features:**
- Automatic reconnection handling
- Event filtering by device or type
- Low-latency updates

**Example:**
```python
import websocket

def on_message(ws, message):
    data = json.loads(message)
    print(f"Device update: {data}")

ws = websocket.WebSocketApp(
    "wss://192.168.1.100:2420/api/v1/ws",
    on_message=on_message
)
ws.run_forever()
```

## Rate Limiting

### Rate Limiting Details

Shure System API implements rate limiting via HTTP 429 responses.

**Rate Limits:**
- Default: 10 requests per second per API client
- Burst capacity: 20 requests (token bucket algorithm)
- Retry-After header indicates wait time

**Headers:**
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 5
X-RateLimit-Reset: 1642854600
Retry-After: 2
```

### Rate Limiter Implementation

The integration includes automatic rate limiting via `micboard.integrations.common.rate_limiter`:

```python
from micboard.integrations.shure.rate_limiter import rate_limit

class ShureDeviceClient:
    @rate_limit(calls_per_second=10.0)
    def get_devices(self) -> list[dict]:
        """Fetch devices with automatic rate limiting."""
        return self._api_request("/api/v1/devices")
```

### Error Handling

Rate limit errors are handled through the exception hierarchy:
- **`ShureAPIRateLimitError`** - Rate limit errors (HTTP 429)
- **`ShureAPIError`** - Generic API errors

Both inherit from base classes in `micboard.integrations.common.exceptions`.

## Data Transformation

### Device Data Mapping

Shure API responses are transformed to micboard's internal format:

```python
# Shure API Response
{
    "device_id": "abc123",
    "device_name": "Handheld 1",
    "model": "ULXD2",
    "status": "online"
}

# Transformed to micboard format
{
    "id": "abc123",
    "name": "Handheld 1",
    "model_name": "ULXD2",
    "online": True
}
```

### Transformer Implementation

```python
from micboard.integrations.shure.transformers import ShureDataTransformer

transformer = ShureDataTransformer()
device_data = transformer.transform_device(shure_response)
```

## Configuration in Django Settings

### Settings Example

```python
# demo/settings.py

MICBOARD = {
    'MANUFACTURERS': {
        'shure': {
            'enabled': True,
            'api_base_url': 'https://192.168.1.100:2420',
            'shared_key': 'your_shared_key_from_system_settings',
            'ssl_verify': False,  # Set to True for production with proper certs
            'poll_interval': 30,  # Seconds between polls
            'timeout': 10,  # Request timeout in seconds
            'websocket_url': None,  # Auto-derived from api_base_url, or override
        }
    }
}
```

### Environment Variables

For production deployments:

```bash
export SHURE_API_BASE_URL="https://192.168.1.100:2420"
export SHURE_SHARED_KEY="your_shared_key"
export SHURE_SSL_VERIFY="false"
export SHURE_POLL_INTERVAL="30"
```

## Troubleshooting

### Connection Refused

**Error:** `Connection refused` when connecting to Shure system
**Cause:** IP address incorrect, system not responding, or System API not enabled
**Solution:**
- Verify Shure system IP address
- Check network connectivity via ping
- Confirm System API is enabled in settings
- Check firewall rules

### Authentication Failed (401)

**Error:** `HTTP 401 Unauthorized`
**Cause:** Invalid shared key or authentication headers missing
**Solution:**
- Verify shared key matches system configuration
- Check authentication header format
- Regenerate shared key if forgotten

### SSL Certificate Verification Failed

**Error:** `SSL: CERTIFICATE_VERIFY_FAILED`
**Cause:** System uses self-signed certificate
**Solution:**
- For development: Set `ssl_verify: False`
- For production: Obtain proper SSL certificates
- Or add certificate to trusted CA store

### Rate Limit Exceeded

**Error:** `HTTP 429 Too Many Requests`
**Cause:** Polling interval too aggressive
**Solution:**
- Increase `poll_interval` in settings
- Reduce API call frequency
- Check for multiple polling processes
- Verify rate limiter is active

### WebSocket Connection Timeout

**Error:** WebSocket connection fails to establish
**Cause:** WebSocket URL incorrect or server rejecting connections
**Solution:**
- Verify WebSocket URL is correctly derived from API base URL
- Check firewall allows WebSocket connections (port 2420)
- Verify system is online and responding
- Check Django Channels configuration

## Best Practices

### Security

1. **Shared Key Management**
   - Use strong, randomly generated shared keys
   - Rotate keys regularly (monthly recommended)
   - Never commit keys to version control
   - Use environment variables in production

2. **SSL/TLS**
   - Use proper SSL certificates for production
   - Enable certificate verification (`ssl_verify: True`)
   - Keep certificates updated

3. **Network Access**
   - Restrict API access to trusted networks
   - Use firewall rules to limit connections
   - Monitor access logs for suspicious activity

### Performance

1. **Polling Optimization**
   - Set appropriate `poll_interval` (30+ seconds recommended)
   - Use WebSocket for real-time updates when possible
   - Implement caching for device lists

2. **Error Handling**
   - Implement exponential backoff for retries
   - Log errors for debugging
   - Alert on API access failures
   - Monitor rate limit headers

3. **Database Efficiency**
   - Use `select_related()` for ForeignKey lookups
   - Use `prefetch_related()` for reverse relationships
   - Batch updates with `bulk_update()`

## Support & Resources

### Shure Documentation
- [Shure System API Explorer](https://shure.secure.force.com/apiexplorer)
- [Shure Developer Portal](https://developer.shure.com)
- [Wireless Microphone Systems Documentation](https://pubs.shure.com)

### Django Micboard Documentation
- [Integration Architecture](development/architecture.md)
- [Plugin Development](archive/plugin-development.md)
- [Rate Limiting](archive/rate-limiting.md)
- [Shure Troubleshooting](guides/shure-troubleshooting.md)
- [Shure Test Suite](archive/SHURE_TEST_SUITE_COMPLETION.md)

### Common Integration Utilities
- **Rate Limiter:** `micboard.integrations.common.rate_limiter`
- **Exceptions:** `micboard.integrations.common.exceptions`
- **Base Client:** `micboard.integrations.base_http_client`

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 26.01.22 | 2026-01-22 | Initial integration documentation with API references |

---

**Last Updated:** January 22, 2026
**Maintainer:** Django Micboard Development Team
**Status:** ✅ Production Ready
