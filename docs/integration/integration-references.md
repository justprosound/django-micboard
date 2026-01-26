# Integration References & API Documentation

**Version:** 26.01.22
**Status:** Current
**Last Updated:** January 22, 2026

## Official Manufacturer API Documentation

### Shure System API

#### Primary Documentation
- **Shure System API**: https://www.shure.com/en-US/products/software/systemapi
- **API Explorer**: https://shure.secure.force.com/apiexplorer
- **Developer Portal**: https://developer.shure.com

#### Authentication
- **Method:** HTTP Digest Authentication
- **Shared Key:** Configured at system level
- **Additional Headers:** `X-Shure-Auth-Key` for enhanced security

#### Key Endpoints
- `GET /api/v1/devices` - List all devices
- `GET /api/v1/devices/{device_id}` - Get device details
- `GET /api/v1/devices/{device_id}/channels` - Get device channels
- `GET /api/v1/devices/{device_id}/transmitter` - Get transmitter data
- `WSS /api/v1/ws` - WebSocket for real-time updates

#### Rate Limiting
- Limit: 10 requests per second (default)
- Burst: 20 requests (token bucket algorithm)
- Header: `Retry-After` indicates wait time

**Integration Guide:** [Shure Integration Guide](./shure-integration.md)

---

### Sennheiser Sound Control Protocol

#### API Specifications
- **TCCM API 1.8 JSON**: https://www.sennheiser.com/globalassets/digizuite/51646-en-tccm-api-1_8.json
- **TC Bar OpenAPI 3.0**: https://www.sennheiser.com/globalassets/digizuite/52626-en-tc-bar-openapi-3rd-party-release-1.12.yaml

#### Documentation
- **Sound Control Protocol**: https://docs.cloud.sennheiser.com/en-us/api-docs/api-docs/sound-control-protocol.html
- **Sound Control Protocol v2 (Draft)**: https://docs.cloud.sennheiser.com/en-us/api-docs/api-docs/resources/Sennheiser%20Sound%20Control%20Protocol%20v2_draft_0.1.html
- **API Docs Portal**: https://docs.cloud.sennheiser.com/en-us/api-docs/api-docs/

#### Device Configuration Requirements

**Factory Default Limitation:**
Sennheiser devices cannot be accessed via API in factory default state.

**Enabling Third-Party API Access:**
1. Connect device to Sennheiser Control Cockpit
2. Navigate to device settings
3. Enable third-party access
4. Configure third-party password

#### Authentication
- **Method:** HTTP Basic Authentication (RFC 7617)
- **Username:** `api` (fixed)
- **Password:** Configured via Sennheiser Control Cockpit
- **Requirement:** Must authenticate with every request

#### Example Authentication
```python
from requests.auth import HTTPBasicAuth

auth = HTTPBasicAuth("api", "configured_password")
response = requests.get(
    "http://device-ip/api/endpoint",
    auth=auth
)
```

**Integration Guide:** [Sennheiser Integration Guide](./sennheiser-integration.md)

---

## Common Integration Utilities

### Shared Rate Limiter

**Module:** `micboard.integrations.common.rate_limiter`

Implements token bucket algorithm using Django cache for consistent rate limiting across all manufacturers.

**Features:**
- Configurable `calls_per_second` parameter
- Thread-safe atomic cache operations
- Django cache backend compatible
- DEBUG logging for rate limit events

**Usage:**
```python
from micboard.integrations.common.rate_limiter import rate_limit

@rate_limit(calls_per_second=10.0)
def api_request(self):
    """Automatically rate limited to 10 requests per second."""
    pass
```

**Reference:** [Rate Limiting Documentation](./rate-limiting.md)

### Base Exception Hierarchy

**Module:** `micboard.integrations.common.exceptions`

Unified exception handling for API errors across all manufacturers.

**Base Classes:**
- `APIError` - Generic API error
- `APIRateLimitError` - Rate limit error (HTTP 429)

**Vendor Subclasses:**
- Shure: `ShureAPIError`, `ShureAPIRateLimitError`
- Sennheiser: `SennheiserAPIError`, `SennheiserAPIRateLimitError`

**Features:**
- HTTP status code tracking
- Response object storage
- Retry-After header parsing
- Formatted error messages

### Base HTTP Client

**Module:** `micboard.integrations.base_http_client`

Abstract base class for HTTP-based API clients.

**Provides:**
- Request/response handling
- Error handling
- Timeout configuration
- SSL verification options

---

## Manufacturer Plugin Architecture

### Plugin Registration

**File:** `micboard/manufacturers/__init__.py`

```python
from micboard.manufacturers import get_manufacturer_plugin

# Dynamically load manufacturer plugin
plugin = get_manufacturer_plugin("shure")
devices = plugin.get_devices()
```

### Available Plugins

| Manufacturer | Module | Status | Notes |
|--------------|--------|--------|-------|
| Shure | `micboard.integrations.shure` | Production | Comprehensive test suite |
| Sennheiser | `micboard.integrations.sennheiser` | Ready | Full API support |

### Adding New Manufacturers

**Reference:** [Plugin Development Guide](../archive/plugin-development.md)

Steps:
1. Create manufacturer directory under `micboard/integrations/`
2. Implement `ManufacturerPlugin` interface
3. Use common utilities (rate limiter, exceptions)
4. Add comprehensive tests
5. Document API integration

---

## Integration Testing

### Test Coverage

**Shure Integration Tests:**
- `test_shure_client.py` - 12 tests covering authentication, WebSocket, health checks
- `test_shure_device_client.py` - 9 tests covering device operations
- `test_shure_transformers.py` - 9 tests covering data transformation
- **Total:** 30 tests, 100% passing

**Test Command:**
```bash
pytest micboard/tests/test_shure_*.py -v
```

### Sennheiser Integration Tests

**Status:** Implementation ready
- Authentication tests
- Device discovery tests
- API operation tests
- Error handling tests

### Running Full Test Suite

```bash
# Run all tests
pytest micboard/tests/ -v

# Run with coverage
pytest micboard/tests/ --cov=micboard

# Run specific manufacturer tests
pytest micboard/tests/ -k "shure" -v
pytest micboard/tests/ -k "sennheiser" -v
```

---

## Docker Demo Environment

**Purpose:** Integrated testing and development environment

**Components:**
- Django app with Micboard
- PostgreSQL database
- Redis cache
- Manufacturer mock APIs

**Reference:** `demo/docker/`

**Usage:**
```bash
docker-compose -f demo/docker/docker-compose.yml up
```

---

## API Response Transformation

### Data Transformation Pipeline

```
Manufacturer API Response
    ↓
Transform to Common Format
    ↓
Store in Django Models
    ↓
Broadcast via WebSocket
    ↓
Frontend Display
```

### Shure Data Transformer

**Module:** `micboard.integrations.shure.transformers.ShureDataTransformer`

Transforms Shure API responses to micboard's internal format.

### Sennheiser Data Transformer

**Module:** `micboard.integrations.sennheiser.transformers.SennheiserDataTransformer`

Transforms Sennheiser API responses to micboard's internal format.

---

## Performance Considerations

### Rate Limiting

**Shure:** 10 req/s default, burst capability
**Sennheiser:** Per device limit

### Polling Strategy

- **Poll Interval:** Configurable (30+ seconds recommended)
- **Batch Operations:** Use bulk_update() for multiple devices
- **Caching:** Implement 30-second cache for device lists

### Database Optimization

```python
# Use select_related for ForeignKey
devices = Device.objects.select_related('manufacturer').all()

# Use prefetch_related for reverse relationships
devices = Device.objects.prefetch_related('channels').all()

# Batch updates
Device.objects.bulk_update(updated_devices, ['status', 'battery'], batch_size=100)
```

---

## Security Best Practices

### Credential Management

1. **Environment Variables**
   ```bash
   export SHURE_API_BASE_URL="https://192.168.1.100:2420"
   export SHURE_SHARED_KEY="your_key"
   export SENNHEISER_HOST="192.168.1.101"
   export SENNHEISER_PASSWORD="your_password"
   ```

2. **Never Hardcode Credentials**
   - Use Django settings from environment
   - Use `.env` files in development only
   - Store secrets in production secret management

3. **SSL/TLS**
   - Enable certificate verification in production
   - Use proper SSL certificates
   - Keep certificates updated

### Network Security

- Restrict API access to trusted networks
- Use firewall rules to limit connections
- Monitor access logs
- Implement rate limiting at network level

---

## Troubleshooting Reference

### Connection Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Connection refused | Wrong IP/port | Verify device address |
| Connection timeout | Network unreachable | Check network connectivity |
| DNS resolution failed | Hostname invalid | Verify hostname in settings |

### Authentication Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| 401 Unauthorized | Invalid credentials | Verify shared key/password |
| 403 Forbidden | API access disabled | Enable API access on device |
| Invalid auth header | Wrong format | Check authentication method |

### Rate Limiting

| Issue | Cause | Solution |
|-------|-------|----------|
| 429 Too Many Requests | Too aggressive polling | Increase poll_interval |
| Rate limit errors | Multiple pollers | Check for duplicate processes |

### SSL/TLS Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Certificate verification failed | Self-signed cert | Set ssl_verify=False (dev only) |
| Certificate expired | Old certificate | Renew certificate |

---

## Quick Reference

### Configuration Templates

**Shure:**
```python
MICBOARD = {
    'MANUFACTURERS': {
        'shure': {
            'enabled': True,
            'api_base_url': 'https://192.168.1.100:2420',
            'shared_key': 'your_shared_key',
            'ssl_verify': False,
            'poll_interval': 30,
        }
    }
}
```

**Sennheiser:**
```python
MICBOARD = {
    'MANUFACTURERS': {
        'sennheiser': {
            'enabled': True,
            'api_base_url': 'http://192.168.1.101',
            'password': 'your_configured_password',
            'ssl_verify': False,
            'poll_interval': 30,
        }
    }
}
```

### Import References

```python
# Common utilities
from micboard.integrations.common import rate_limit, APIError, APIRateLimitError

# Shure
from micboard.integrations.shure.client import ShureSystemAPIClient
from micboard.integrations.shure.device_client import ShureDeviceClient
from micboard.integrations.shure.exceptions import ShureAPIError, ShureAPIRateLimitError

# Sennheiser
from micboard.integrations.sennheiser.client import SennheiserAPIClient
from micboard.integrations.sennheiser.exceptions import SennheiserAPIError, SennheiserAPIRateLimitError

# Manufacturer plugin
from micboard.manufacturers import get_manufacturer_plugin
```

---

## Related Documentation

- [Architecture Overview](../development/architecture.md)
- [Shure Integration Guide](../shure-integration.md)
- [Sennheiser Integration Guide](../archive/sennheiser-integration.md)
- [Plugin Development](../archive/plugin-development.md)
- [Rate Limiting](../archive/rate-limiting.md)
- [Shure Troubleshooting](../guides/shure-troubleshooting.md)

---

**Last Updated:** January 22, 2026
**Maintainer:** Django Micboard Development Team
**Status:** ✅ Current & Complete
