# Shure System API Troubleshooting Guide

This guide helps diagnose and resolve common issues when integrating django-micboard with Shure wireless microphone systems via the Shure System API.

## Table of Contents

- [Connection Issues](#connection-issues)
- [Authentication Problems](#authentication-problems)
- [Network GUID Discovery](#network-guid-discovery)
- [Device Polling Delays](#device-polling-delays)
- [Data Transformation Errors](#data-transformation-errors)
- [WebSocket Connection Issues](#websocket-connection-issues)
- [Rate Limiting](#rate-limiting)
- [Performance Optimization](#performance-optimization)

---

## Connection Issues

### Symptom: "Connection refused" or "Connection timeout"

**Cause:** Cannot reach Shure System API endpoint.

**Diagnostic Steps:**

1. **Verify API is running:**
   ```bash
   curl http://<device-ip>:8080/api/v1/devices
   ```

2. **Check network connectivity:**
   ```bash
   ping <device-ip>
   ```

3. **Verify firewall rules:**
   - Ensure port 8080 (HTTP) and 8443 (HTTPS) are open
   - Check both local firewall and network firewall rules

4. **Test from Django shell:**
   ```python
   from micboard.integrations.shure.client import ShureSystemAPIClient
   client = ShureSystemAPIClient()
   health = client.check_health()
   print(health)
   ```

**Solutions:**

- **Local network:** Ensure micboard server and Shure devices are on same VLAN
- **VPN scenario:** Configure VPN split tunneling or direct routes
- **Docker:** Use `host` network mode or ensure proper port mapping
- **SSL/TLS:** If using HTTPS, verify certificate validity or disable SSL verification in config:
  ```python
  MICBOARD_CONFIG = {
      'SHURE_API_VERIFY_SSL': False,  # Use with caution
  }
  ```

---

## Authentication Problems

### Symptom: "401 Unauthorized" or "403 Forbidden"

**Cause:** Missing or invalid shared key authentication.

**Diagnostic Steps:**

1. **Verify shared key is configured:**
   ```python
   from django.conf import settings
   config = settings.MICBOARD_CONFIG
   print(config.get('SHURE_API_SHARED_KEY'))  # Should not be None/empty
   ```

2. **Test authentication manually:**
   ```bash
   curl -H "Authorization: Bearer YOUR_SHARED_KEY" \
        -H "x-api-key: YOUR_SHARED_KEY" \
        http://<device-ip>:8080/api/v1/devices
   ```

3. **Check device API settings:**
   - Log into Shure device web UI
   - Navigate to **Settings > Network > API**
   - Verify API is enabled and shared key matches

**Solutions:**

- **Generate new shared key** in Shure device settings if forgotten
- **Update micboard config** with correct shared key:
  ```python
  MICBOARD_CONFIG = {
      'SHURE_API_SHARED_KEY': 'your-actual-shared-key-here',
  }
  ```
- **Restart Django** after config changes to reload settings

---

## Network GUID Discovery

### Symptom: Devices appear in discovery but cannot be managed

**Cause:** Shure System API requires `network_guid` parameter for multi-device management, but discovery doesn't always provide it.

**Background:**
The Shure System API uses a `network_guid` to identify device groups. When managing multiple devices (e.g., ULXD4Q with 4 channels), the API requires this GUID to route commands correctly.

**Diagnostic Steps:**

1. **Check if network_guid is returned:**
   ```python
   from micboard.integrations.shure.client import ShureSystemAPIClient
   client = ShureSystemAPIClient()
   devices = client.devices.get_devices()
   for device in devices:
       print(f"Device {device.get('id')}: network_guid = {device.get('network_guid')}")
   ```

2. **Test direct device API call:**
   ```bash
   curl http://<device-ip>:8080/api/v1/devices/<device-id>
   ```
   Look for `networkGuid` or `network_guid` in response.

**Solutions:**

- **Use device identity endpoint** to fetch network_guid:
  ```python
  identity = client.devices.get_device_identity(device_id)
  network_guid = identity.get('network_guid')
  ```

- **Fallback to device-specific API** for older firmware:
  - Some Shure firmware versions don't support network_guid
  - Use device IP-specific endpoints instead of centralized API
  - Example: `http://192.168.1.100/api/v1/devices` vs `http://api-server/api/v1/devices?network_guid=...`

- **Firmware upgrade:** Update Shure devices to latest firmware for full API support

**Known Limitations:**

| Device Model | Firmware Version | network_guid Support |
|--------------|------------------|----------------------|
| ULXD4D/Q     | ≥ 2.7.0          | ✅ Yes               |
| QLXD4        | ≥ 2.5.0          | ✅ Yes               |
| UHF-R        | All              | ❌ No (legacy)       |
| Axient Digital | ≥ 1.6.0        | ✅ Yes               |

---

## Device Polling Delays

### Symptom: Device data takes 30+ seconds to appear

**Cause:** Polling command runs sequentially, rate limiting slows down queries.

**Diagnostic Steps:**

1. **Check polling performance:**
   ```bash
   python manage.py poll_devices --verbosity 2
   ```
   Look for timing logs:
   ```
   Polling shure took 15.3s
   Polling sennheiser took 8.7s
   ```

2. **Identify bottlenecks:**
   - High latency to devices (>200ms)
   - Rate limiting (5 req/s per device)
   - Large number of devices (>20)
   - Complex channel data retrieval

**Solutions:**

- **Optimize polling frequency:**
  ```python
  # In poll_devices management command
  POLL_INTERVAL = 10  # Reduce from default 5s if many devices
  ```

- **Use discovery efficiently:**
  - Cache device IPs to avoid repeated CIDR scans
  - Poll only active/online devices
  - Skip offline devices after 3 failures

- **Adjust rate limits** (use cautiously):
  ```python
  # In micboard/integrations/shure/device_client.py
  @rate_limit(calls_per_second=10.0)  # Increase from 5.0 if API can handle it
  def get_device(self, device_id: str):
      ...
  ```

- **Parallel polling** (future enhancement):
  - Use asyncio for concurrent device queries
  - Currently Django-Q tasks are sequential

**Expected Performance:**

| Device Count | Expected Polling Time | Notes                    |
|--------------|-----------------------|--------------------------|
| 1-5          | 2-5 seconds           | Optimal                  |
| 10-20        | 8-12 seconds          | Good                     |
| 20-50        | 15-30 seconds         | Consider optimization    |
| 50+          | 30+ seconds           | Requires async refactor  |

---

## Data Transformation Errors

### Symptom: "Device data missing 'id' field" in logs

**Cause:** Shure API response format doesn't match expected structure.

**Diagnostic Steps:**

1. **Enable debug logging:**
   ```python
   LOGGING = {
       'loggers': {
           'micboard.integrations.shure.transformers': {
               'level': 'DEBUG',
           },
       },
   }
   ```

2. **Capture raw API response:**
   ```python
   import logging
   logger = logging.getLogger(__name__)

   raw_data = client.devices.get_device(device_id)
   logger.debug(f"Raw device data: {raw_data}")
   ```

3. **Validate against test fixtures:**
   - See `docs/SHURE_API_INTEGRATION_TEST_PLAN.md` for expected format
   - Compare actual response to `MOCK_SHURE_DEVICE` fixture

**Solutions:**

- **Update transformer for API version:**
  - Shure sometimes changes field names between firmware versions
  - Check `micboard/integrations/shure/transformers.py` for field mappings
  - Add fallback field names (e.g., `device_id` vs `id`, `ip_address` vs `ipAddress`)

- **Handle missing fields gracefully:**
  ```python
  # In ShureDataTransformer.transform_device_data()
  device_id = api_data.get("id") or api_data.get("device_id")
  if not device_id:
      logger.warning("Missing device ID, skipping device")
      return None
  ```

- **Report API format changes:**
  - If Shure API format differs from documentation, file issue at [django-micboard repo](https://github.com/yourusername/django-micboard/issues)

**Common Field Variations:**

| Field (camelCase) | Field (snake_case) | micboard Name |
|-------------------|--------------------|---------------|
| `id`              | `device_id`        | `id`          |
| `ipAddress`       | `ip_address`       | `ip`          |
| `modelName`       | `model_name`       | `name`        |
| `firmwareVersion` | `firmware_version` | `firmware`    |
| `serialNumber`    | `serial_number`    | `serial`      |

---

## WebSocket Connection Issues

### Symptom: Real-time updates not working

**Cause:** WebSocket connection to Shure API fails or disconnects.

**Diagnostic Steps:**

1. **Test WebSocket endpoint:**
   ```bash
   # Using websocat (install: cargo install websocat)
   websocat ws://<device-ip>:8080/api/v1/subscriptions/websocket/create
   ```

2. **Check micboard WebSocket consumer:**
   ```python
   # In Django shell
   from micboard.websockets.consumers import DeviceDataConsumer
   # WebSocket URL should be ws://localhost:8000/ws/devices/
   ```

3. **Verify Channels configuration:**
   ```python
   # In demo/asgi.py
   from channels.routing import ProtocolTypeRouter, URLRouter
   # Ensure 'websocket' protocol is configured
   ```

**Solutions:**

- **Configure WebSocket URL explicitly:**
  ```python
  MICBOARD_CONFIG = {
      'SHURE_API_WEBSOCKET_URL': 'ws://<device-ip>:8080/api/v1/subscriptions/websocket/create',
  }
  ```

- **Use HTTPS/WSS for secure connections:**
  ```python
  MICBOARD_CONFIG = {
      'SHURE_API_BASE_URL': 'https://<device-ip>:8443',
      # WebSocket URL is auto-derived as wss://<device-ip>:8443/...
  }
  ```

- **Handle reconnection logic:**
  - WebSocket consumer should auto-reconnect on disconnect
  - Check `micboard/websockets/` for reconnection handling
  - Verify no firewall blocking WebSocket upgrade

- **Test with simple WebSocket client:**
  ```javascript
  // In browser console
  const ws = new WebSocket('ws://localhost:8000/ws/devices/');
  ws.onmessage = (event) => console.log('Message:', event.data);
  ```

---

## Rate Limiting

### Symptom: "429 Too Many Requests" errors

**Cause:** Exceeded Shure API rate limits.

**Diagnostic Steps:**

1. **Check error details:**
   ```python
   try:
       client.devices.get_device(device_id)
   except ShureAPIRateLimitError as e:
       print(f"Rate limited. Retry after: {e.retry_after}s")
   ```

2. **Monitor request frequency:**
   ```bash
   # Enable request logging
   LOGGING = {
       'loggers': {
           'micboard.integrations.base_http_client': {
               'level': 'DEBUG',
           },
       },
   }
   ```

**Solutions:**

- **Respect retry-after header:**
  - ShureAPIRateLimitError includes `retry_after` attribute
  - Implement exponential backoff in polling logic

- **Reduce polling frequency:**
  ```python
  # Adjust rate limiter in device_client.py
  @rate_limit(calls_per_second=2.0)  # Reduce from 5.0
  def get_device(self, device_id: str):
      ...
  ```

- **Batch operations:**
  - Use `/api/v1/devices` to get all devices in one call
  - Avoid calling `/api/v1/devices/{id}` repeatedly

- **Cache device data:**
  ```python
  # In PollingService
  def poll_manufacturer(self, manufacturer_code):
      # Cache device list for 30 seconds
      cache_key = f"shure_devices_{manufacturer_code}"
      devices = cache.get(cache_key)
      if not devices:
          devices = plugin.get_devices()
          cache.set(cache_key, devices, timeout=30)
  ```

**Shure API Rate Limits (Estimated):**

| Endpoint                           | Limit         | Notes                  |
|------------------------------------|---------------|------------------------|
| `/api/v1/devices`                  | 10 req/min    | List all devices       |
| `/api/v1/devices/{id}`             | 60 req/min    | Get single device      |
| `/api/v1/devices/{id}/channels`    | 60 req/min    | Get device channels    |
| `/api/v1/devices/{id}/channels/{ch}/tx` | 120 req/min | Get transmitter data |

**Note:** Actual limits may vary by firmware version and device model.

---

## Performance Optimization

### Tips for Large Deployments

**1. Database Indexing:**
```python
# Ensure indexes on frequently queried fields
class Receiver(models.Model):
    api_device_id = models.CharField(max_length=255, db_index=True)
    manufacturer = models.ForeignKey(Manufacturer, on_delete=models.CASCADE, db_index=True)
    online = models.BooleanField(default=False, db_index=True)
```

**2. Query Optimization:**
```python
# Use select_related/prefetch_related
receivers = Receiver.objects.filter(online=True).select_related('manufacturer', 'location')
```

**3. Async Polling (Future):**
```python
# Convert to async/await for concurrent device queries
async def poll_devices_async(self):
    tasks = [self.poll_device(device_id) for device_id in device_ids]
    results = await asyncio.gather(*tasks)
```

**4. Redis Caching:**
```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}
```

**5. Monitoring:**
- Use Django Debug Toolbar to identify slow queries
- Monitor API request timing with Prometheus/Grafana
- Set up alerts for polling failures

---

## Getting Help

If issues persist after following this guide:

1. **Check logs:** Enable DEBUG logging for `micboard.integrations.shure`
2. **Run tests:** `pytest micboard/tests/test_shure*.py -v`
3. **Review docs:**
   - [Shure Integration Testing](shure-integration-testing.md)
   - [Shure API Integration Test Plan](SHURE_API_INTEGRATION_TEST_PLAN.md)
4. **Report issues:** [GitHub Issues](https://github.com/yourusername/django-micboard/issues)

**Include in bug reports:**
- Django and Python versions
- Shure device model and firmware version
- Relevant log excerpts (with sensitive data redacted)
- Steps to reproduce
- Expected vs actual behavior
