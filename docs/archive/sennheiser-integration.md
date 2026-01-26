# Sennheiser Integration Guide

**Version:** 26.01.22
**Status:** Integration Ready
**Last Updated:** January 22, 2026

## API Documentation References

### Official Sennheiser API Specifications

#### TCCM API
- **Format:** JSON Schema
- **Download:** [TCCM API 1.8 Specification](https://www.sennheiser.com/globalassets/digizuite/51646-en-tccm-api-1_8.json)
- **Purpose:** Team Communication & Collaboration Management API

#### TC Bar OpenAPI
- **Format:** OpenAPI 3.0 YAML
- **Download:** [TC Bar OpenAPI 3rd Party Release 1.12](https://www.sennheiser.com/globalassets/digizuite/52626-en-tc-bar-openapi-3rd-party-release-1.12.yaml)
- **Purpose:** TC Bar device API specification for third-party integrations

#### Sound Control Protocol
- **Documentation:** [Sound Control Protocol Documentation](https://docs.cloud.sennheiser.com/en-us/api-docs/api-docs/sound-control-protocol.html)
- **Status:** Current version documentation
- **Purpose:** Core protocol for device communication

#### Sound Control Protocol v2 Draft
- **Documentation:** [Sennheiser Sound Control Protocol v2 (Draft 0.1)](https://docs.cloud.sennheiser.com/en-us/api-docs/api-docs/resources/Sennheiser%20Sound%20Control%20Protocol%20v2_draft_0.1.html)
- **Status:** Draft specification
- **Purpose:** Next-generation protocol specification (preview)

## Device Configuration

### Factory Default Limitation

**Important:** Sennheiser devices cannot be accessed via API in their factory default state. Third-party API access must be explicitly enabled.

### Enabling API Access

To enable third-party API access on a Sennheiser device:

1. **Connect to Sennheiser Control Cockpit**
   - Install Sennheiser Control Cockpit software (if not already installed)
   - Connect the Sennheiser device to the network
   - Launch Control Cockpit and discover the device

2. **Navigate to Device Settings**
   - Open the device management page in Control Cockpit
   - Locate the device you want to enable for API access

3. **Configure Third-Party Access**
   - In the device settings, find the "Third-party access" or "API access" option
   - Enable third-party access
   - Configure a strong third-party password for authentication

4. **Secure the Password**
   - Store the configured password securely
   - Use it for all API authentication requests
   - Do not share with unauthorized users

## Authentication

### HTTP Basic Authentication

All Sennheiser API requests require HTTP Basic Authentication.

**Authentication Requirements:**
- **Method:** HTTP Basic Authentication (RFC 7617)
- **Username:** `api` (fixed)
- **Password:** Configured via Sennheiser Control Cockpit

**Mandatory:** Authentication credentials must be included with every request to the Sennheiser device.

### Authentication Header Format

```
Authorization: Basic base64(api:configured_password)
```

### Implementation in Python/Requests

```python
import requests
from requests.auth import HTTPBasicAuth

# Configure authentication
username = "api"
password = "your_configured_password"  # Set in Control Cockpit

# Make authenticated request
response = requests.get(
    "http://device-ip/api/endpoint",
    auth=HTTPBasicAuth(username, password)
)
```

### Django Implementation

In micboard's Sennheiser integration:

```python
from requests.auth import HTTPBasicAuth

class SennheiserAPIClient(BaseHTTPClient):
    def __init__(self, host: str, password: str, *, ssl_verify: bool = True):
        """
        Initialize Sennheiser API client.

        Args:
            host: Device IP or hostname
            password: Third-party password configured in Control Cockpit
            ssl_verify: Whether to verify SSL certificates (default: True)
        """
        self.host = host
        self.password = password
        self.ssl_verify = ssl_verify
        self.auth = HTTPBasicAuth("api", password)

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make authenticated request to Sennheiser device."""
        url = f"http://{self.host}/api{endpoint}"
        response = requests.request(
            method,
            url,
            auth=self.auth,
            verify=self.ssl_verify,
            **kwargs
        )
        return response.json()
```

## Integration Features

### Supported Operations

- Device discovery and identification
- Real-time status monitoring
- Battery level tracking
- Signal strength monitoring
- Channel configuration
- Device firmware information

### Rate Limiting

Sennheiser devices implement rate limiting via HTTP 429 responses. The integration includes:
- **Automatic retry logic** with exponential backoff
- **Rate-aware polling** to respect device limits
- **Shared rate limiter** via `micboard.integrations.common.rate_limiter`

### Error Handling

Sennheiser API errors are handled through the common exception hierarchy:
- **`SennheiserAPIError`** - Generic API errors
- **`SennheiserAPIRateLimitError`** - Rate limit errors (HTTP 429)

Both inherit from base classes in `micboard.integrations.common.exceptions`.

## API Response Format

### Device List Response

```json
{
  "devices": [
    {
      "id": "device-uuid",
      "name": "Sennheiser Device",
      "model": "TC Bar",
      "status": "online",
      "battery_level": 85,
      "signal_strength": -50
    }
  ]
}
```

### Device Status Response

```json
{
  "id": "device-uuid",
  "status": "online",
  "last_seen": "2026-01-22T10:30:00Z",
  "battery_level": 85,
  "signal_strength": -50,
  "channels": [
    {
      "id": 1,
      "name": "Channel 1",
      "frequency": 500000000,
      "status": "active"
    }
  ]
}
```

## Configuration in Django Settings

### Settings Example

```python
# demo/settings.py

MICBOARD = {
    'MANUFACTURERS': {
        'sennheiser': {
            'enabled': True,
            'api_base_url': 'http://192.168.1.100',  # Device IP or hostname
            'password': 'your_third_party_password',  # Set in Control Cockpit
            'ssl_verify': False,  # Set to True if using HTTPS
            'poll_interval': 30,  # Seconds between polls
            'timeout': 10,  # Request timeout in seconds
        }
    }
}
```

### Environment Variables

For production deployments, use environment variables:

```bash
export SENNHEISER_API_HOST="192.168.1.100"
export SENNHEISER_API_PASSWORD="your_configured_password"
export SENNHEISER_SSL_VERIFY="false"
export SENNHEISER_POLL_INTERVAL="30"
```

## Troubleshooting

### Connection Refused

**Error:** `Connection refused` when connecting to device
**Cause:** Device IP is incorrect or device is not reachable
**Solution:**
- Verify device IP address
- Check network connectivity
- Ensure device is powered on and connected to network

### Authentication Failed (401)

**Error:** `HTTP 401 Unauthorized`
**Cause:** Invalid password or wrong username
**Solution:**
- Verify password matches what was configured in Control Cockpit
- Ensure username is `api` (case-sensitive)
- Reconfigure password in Control Cockpit if forgotten

### API Access Disabled

**Error:** `HTTP 403 Forbidden` or `Access Denied`
**Cause:** Third-party API access not enabled on device
**Solution:**
- Connect device to Sennheiser Control Cockpit
- Navigate to device settings
- Enable third-party API access
- Configure third-party password

### Rate Limit Exceeded

**Error:** `HTTP 429 Too Many Requests`
**Cause:** Polling interval too aggressive
**Solution:**
- Increase `poll_interval` in settings
- Reduce frequency of API calls
- Check for multiple polling instances

### SSL Certificate Verification Failed

**Error:** `SSL: CERTIFICATE_VERIFY_FAILED`
**Cause:** Device uses self-signed certificate or SSL verification is enabled
**Solution:**
- Set `ssl_verify: False` in settings for development
- For production, obtain proper SSL certificates for device
- Or set `ssl_verify: False` if using internal network

## Best Practices

### Security

1. **Strong Passwords**
   - Use strong third-party passwords (minimum 12 characters)
   - Include uppercase, lowercase, numbers, and special characters

2. **Credential Management**
   - Never hardcode passwords in code
   - Use environment variables for sensitive data
   - Rotate passwords regularly

3. **Network Security**
   - Place Sennheiser devices on separate VLAN if possible
   - Use firewall rules to restrict API access
   - Monitor API access logs for suspicious activity

### Performance

1. **Polling Optimization**
   - Set appropriate `poll_interval` (30+ seconds recommended)
   - Use caching to reduce API calls
   - Batch requests when possible

2. **Error Handling**
   - Implement exponential backoff for retries
   - Log errors for debugging
   - Alert on API access failures

3. **Rate Limiting**
   - Respect device rate limits (typically 10-20 req/s)
   - Use shared rate limiter from `micboard.integrations.common`
   - Monitor rate limit headers in responses

## Support & Resources

### Sennheiser Documentation
- [Official Sennheiser Docs Portal](https://docs.cloud.sennheiser.com)
- [API Reference](https://docs.cloud.sennheiser.com/en-us/api-docs/api-docs/)
- [Sound Control Protocol](https://docs.cloud.sennheiser.com/en-us/api-docs/api-docs/sound-control-protocol.html)

### Django Micboard Documentation
- [Integration Architecture](./architecture.md)
- [Plugin Development](./plugin-development.md)
- [Rate Limiting](./rate-limiting.md)

### Common Integration Utilities
- **Rate Limiter:** `micboard.integrations.common.rate_limiter`
- **Exceptions:** `micboard.integrations.common.exceptions`
- **Base Client:** `micboard.integrations.base_http_client`

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 26.01.22 | 2026-01-22 | Initial integration documentation |

---

**Last Updated:** January 22, 2026
**Maintainer:** Django Micboard Development Team
**Status:** ✅ Production Ready
