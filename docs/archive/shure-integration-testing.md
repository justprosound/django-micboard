# Shure System API Integration - Testing & Implementation Guide

**Version:** 25.10.17
**Date:** January 22, 2026
**Status:** Active Development

## Overview

This document provides comprehensive details on django-micboard's integration with the Shure System API, including all API endpoints used, authentication requirements, data flow, testing requirements, and known limitations.

## Table of Contents

1. [Shure System API Endpoints](#shure-system-api-endpoints)
2. [Authentication & Configuration](#authentication--configuration)
3. [Device Discovery Flow](#device-discovery-flow)
4. [Device Lifecycle (Add/Move/Change)](#device-lifecycle-addmovechange)
5. [Polling & Data Sync](#polling--data-sync)
6. [WebSocket Real-Time Updates](#websocket-real-time-updates)
7. [Error Handling & Rate Limiting](#error-handling--rate-limiting)
8. [Testing Requirements](#testing-requirements)
9. [Known Issues & Limitations](#known-issues--limitations)
10. [Docker Demo Configuration](#docker-demo-configuration)

---

## Shure System API Endpoints

### Device Endpoints

| Endpoint | Method | Purpose | Rate Limit | Used By |
|----------|--------|---------|------------|---------|
| `/api/v1/devices` | GET | List all devices | 5 req/s | `ShureDeviceClient.get_devices()` |
| `/api/v1/devices/models` | GET | Supported device models | 5 req/s | `ShureDeviceClient.get_supported_device_models()` |
| `/api/v1/devices/{id}` | GET | Device details | 10 req/s | `ShureDeviceClient.get_device()` |
| `/api/v1/devices/{id}/channels` | GET | Channel data | 10 req/s | `ShureDeviceClient.get_device_channels()` |
| `/api/v1/devices/{id}/channels/{ch}/tx` | GET | Transmitter data | 10 req/s | `ShureDeviceClient.get_transmitter_data()` |
| `/api/v1/devices/{id}/identify` | GET | Device identity | 10 req/s | `ShureDeviceClient.get_device_identity()` |
| `/api/v1/devices/{id}/network` | GET | Network info (MAC, hostname) | 10 req/s | `ShureDeviceClient.get_device_network()` |
| `/api/v1/devices/{id}/status` | GET | Device status | 10 req/s | `ShureDeviceClient.get_device_status()` |

### Discovery Configuration Endpoints

| Endpoint | Method | Purpose | Used By |
|----------|--------|---------|---------|
| `/api/v1/config/discovery/ips` | GET | Retrieve manual discovery IPs | `ShureDiscoveryClient.get_discovery_ips()` |
| `/api/v1/config/discovery/ips` | PUT | Set manual discovery IPs | `ShureDiscoveryClient.add_discovery_ips()` |
| `/api/v1/config/discovery/ips/remove` | PATCH/POST | Remove discovery IPs | `ShureDiscoveryClient.remove_discovery_ips()` |

### WebSocket Endpoints

| Endpoint | Method | Purpose | Used By |
|----------|--------|---------|---------|
| `/api/v1/subscriptions/websocket/create` | POST | Create WS transport | `ShureWebSocketClient` |
| `/api/v1/devices/{id}/identify/subscription/{transport_id}` | POST | Subscribe to device updates | `connect_and_subscribe()` |

---

## Authentication & Configuration

### Required Environment Variables

```bash
# Shure System API base URL
MICBOARD_SHURE_API_BASE_URL=http://172.21.x.x:10000

# Shared key for authentication (REQUIRED)
MICBOARD_SHURE_API_SHARED_KEY=your_shared_key_here

# SSL verification (set to 'false' for self-signed certs)
MICBOARD_SHURE_API_VERIFY_SSL=true

# WebSocket URL (optional - auto-derived from base URL)
MICBOARD_SHURE_API_WEBSOCKET_URL=ws://172.21.x.x:10000

# Network timeouts
MICBOARD_NETWORK_TIMEOUT=30
MICBOARD_POLLING_INTERVAL=60
```

### Authentication Mechanism

Shure System API uses **shared key authentication** via HTTP headers:

```python
headers = {
    "Authorization": f"Bearer {shared_key}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}
```

**Implementation:** `micboard/integrations/shure/client.py` - `ShureSystemAPIClient._configure_authentication()`

### Health Check

Endpoint used for health verification:
- **Primary:** `/api/v1/devices` (checks connectivity + auth)
- **Returns:** List of devices or 401 Unauthorized

---

## Device Discovery Flow

### 1. Manual IP Discovery Configuration

```python
# Add IPs to Shure System API discovery list
client.discovery.add_discovery_ips(["172.21.1.100", "172.21.1.101"])

# Retrieve current discovery IPs
ips = client.discovery.get_discovery_ips()

# Remove IPs
client.discovery.remove_discovery_ips(["172.21.1.100"])
```

**API Calls:**
1. `GET /api/v1/config/discovery/ips` - Fetch current IPs
2. `PUT /api/v1/config/discovery/ips` - Set combined list (existing + new)
3. `PATCH /api/v1/config/discovery/ips/remove` - Remove specific IPs

### 2. Device Detection

Shure System API automatically discovers devices on configured networks. Django-micboard polls for new devices:

```python
devices = client.devices.get_devices()
# Returns list of device objects with:
# - device_id
# - model
# - serial_number
# - ip_address
# - status
```

### 3. Device Enrichment

For each discovered device, fetch additional data:

```python
device_data = client.devices.get_device(device_id)
identity = client.devices.get_device_identity(device_id)
network = client.devices.get_device_network(device_id)
channels = client.devices.get_device_channels(device_id)
```

### 4. Model Creation

Transform Shure API data to micboard models:

```python
# Via ShureDataTransformer
micboard_data = transformer.transform_device_data(api_data)

# Create/update Receiver model
receiver, created = Receiver.objects.update_or_create(
    api_device_id=micboard_data["api_device_id"],
    manufacturer=manufacturer,
    defaults=micboard_data
)
```

---

## Device Lifecycle (Add/Move/Change)

### Add Device

**Flow:**
1. Device discovered via Shure API polling
2. Transform API data to micboard format
3. Create `Receiver` model with `api_device_id`
4. Create related `Channel` models
5. Optionally link `Transmitter` models
6. Broadcast WebSocket event: `device_added`

**Service:** `micboard.services.device_lifecycle.DeviceLifecycleManager.handle_device_lifecycle()`

**Test Scenario:**
```python
# Ensure device appears in database after discovery
# Verify all fields populated correctly
# Confirm WebSocket broadcast sent
```

### Move Device

**Triggers:**
- IP address change detected
- Location assignment change

**Flow:**
1. Detect IP/location change in polling cycle
2. Log to `DeviceMovementLog`
3. Update `Receiver.ip` and/or location fields
4. Calculate uptime impact
5. Broadcast WebSocket event: `device_moved`

**Service:** `micboard.services.device_service.DeviceService.track_device_movement()`

**Test Scenario:**
```python
# Change device IP in Shure API
# Verify DeviceMovementLog created
# Confirm Receiver.ip updated
# Check WebSocket broadcast
```

### Change Device

**Triggers:**
- Battery level change
- Signal quality change
- Channel configuration change
- Device name change

**Flow:**
1. Detect field changes in polling data
2. Update `Receiver` model fields
3. Log changes in `ConfigurationAuditLog` if applicable
4. Broadcast WebSocket event: `device_updated`

**Service:** `micboard.services.polling_service.PollingService.poll_manufacturer()`

**Test Scenario:**
```python
# Modify device settings in Shure API
# Verify model updates in database
# Check audit log entries
# Confirm WebSocket broadcasts
```

---

## Polling & Data Sync

### Polling Schedule

**Default:** Every 60 seconds
**Configurable:** `MICBOARD_POLLING_INTERVAL` environment variable

### Polling Process

```python
# management/commands/poll_devices.py
1. Fetch all active manufacturers
2. For each manufacturer:
   a. Get plugin instance
   b. Call plugin.get_devices()
   c. Transform device data
   d. Update/create Receiver models
   e. Update Channel and Transmitter models
   f. Broadcast updates via WebSocket
```

### Data Transformation

**Implementation:** `micboard/integrations/shure/transformers.py`

Key transformations:
- `device_id` → `api_device_id`
- `battery_percentage` → normalized 0-100
- `rf_signal_quality` → normalized 0-100
- `is_online` → boolean from status
- `firmware_version` → string

### Deduplication

**Service:** `micboard.services.deduplication_service.DeduplicationService`

Rules:
1. Match by `api_device_id` (primary)
2. Match by `serial_number` + `manufacturer`
3. Match by `ip` + `manufacturer` (with caution)

---

## WebSocket Real-Time Updates

### Shure WebSocket Flow

1. **Create Transport:**
   ```
   POST /api/v1/subscriptions/websocket/create
   Response: {"transport_id": "abc123", "ws_url": "ws://..."}
   ```

2. **Connect WebSocket:**
   ```python
   async with websockets.connect(ws_url) as ws:
       # Handle messages
   ```

3. **Subscribe to Device:**
   ```
   POST /api/v1/devices/{id}/identify/subscription/{transport_id}
   ```

4. **Receive Updates:**
   ```json
   {
     "device_id": "XXXXXXXX",
     "event": "device_update",
     "data": { ... }
   }
   ```

### Django Channels Integration

**Consumer:** `micboard/websockets/consumers.py`

Broadcast events:
- `device.added`
- `device.updated`
- `device.moved`
- `device.removed`
- `battery.low`
- `signal.loss`

---

## Error Handling & Rate Limiting

### Rate Limiting

**Implementation:** `micboard/integrations/shure/rate_limiter.py`

Configured limits:
- Device list: 5 req/s
- Device details: 10 req/s
- Channel/transmitter: 10 req/s

**Decorator:**
```python
@rate_limit(calls_per_second=5.0)
def get_devices(self):
    # Rate-limited call
```

### Error Handling

**Exception Hierarchy:**
```python
ShureAPIError (base)
├── ShureAuthenticationError (401)
├── ShureRateLimitError (429)
├── ShureConnectionError (network issues)
└── ShureWebSocketError (WS issues)
```

**Retry Strategy:**
- Max retries: 3
- Backoff: Exponential (1s, 2s, 4s)
- Retry on: 500, 502, 503, 504

---

## Testing Requirements

### Unit Tests

**File:** `micboard/tests/test_shure_integration.py`

Required test coverage:

1. **Authentication Tests**
   - Valid credentials → success
   - Invalid credentials → `ShureAuthenticationError`
   - Missing credentials → configuration error

2. **Device Discovery Tests**
   - Add discovery IPs → verify API call
   - Get discovery IPs → verify response parsing
   - Remove discovery IPs → verify API call

3. **Device Polling Tests**
   - Fetch devices → verify data transformation
   - Handle empty response
   - Handle malformed data

4. **Rate Limiting Tests**
   - Exceed rate limit → backoff behavior
   - Concurrent requests → queue properly

5. **Error Handling Tests**
   - Connection timeout → retry
   - 401 Unauthorized → raise auth error
   - 429 Too Many Requests → backoff
   - 500 Server Error → retry

6. **Data Transformation Tests**
   - Shure API format → micboard format
   - Missing fields → defaults applied
   - Invalid data → logged + skipped

### Integration Tests

**Requirements:**

1. **Live API Connection**
   - Connect to real Shure System API
   - Verify SSL/TLS handling
   - Test authentication flow

2. **Device Lifecycle**
   - Add device via discovery
   - Verify model creation
   - Update device data
   - Move device (IP change)
   - Remove device

3. **WebSocket Subscriptions**
   - Establish WS connection
   - Subscribe to device updates
   - Receive real-time events
   - Handle reconnection

4. **Polling Behavior**
   - Run poll_devices command
   - Verify database updates
   - Check WebSocket broadcasts
   - Validate audit logs

### Mock vs Live Testing

**Environment Variable:**
```bash
# Use mocked Shure API responses
MICBOARD_TEST_MODE=mock

# Use live Shure System API
MICBOARD_TEST_MODE=live
MICBOARD_SHURE_API_BASE_URL=http://172.21.x.x:10000
MICBOARD_SHURE_API_SHARED_KEY=your_key
```

---

## Known Issues & Limitations

### 1. Network GUID Issue

**Problem:** Shure System API may return inconsistent `network_guid` values across requests.

**Impact:** Device deduplication may fail if relying solely on `network_guid`.

**Workaround:** Use `api_device_id` or `serial_number` as primary identifiers.

**Reference:** `docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md`

### 2. Discovery Race Conditions

**Problem:** Devices may appear/disappear during discovery if network is unstable.

**Impact:** Spurious "device removed" events.

**Mitigation:**
- Implement grace period before marking devices offline
- Use `last_seen` timestamp with tolerance window

### 3. Polling Delays

**Problem:** High device count (>100) causes polling to exceed interval.

**Impact:** Stale data, missed updates.

**Solution:**
- Implement concurrent polling per manufacturer
- Use Django-Q for distributed task execution
- Reduce polling interval for critical devices

### 4. WebSocket Reconnection

**Problem:** WebSocket connections drop after ~5 minutes of inactivity.

**Impact:** Missing real-time updates.

**Solution:**
- Implement ping/pong keepalive
- Auto-reconnect with exponential backoff
- Fall back to polling if WS unavailable

### 5. Rate Limit Enforcement

**Problem:** Shure API rate limits not clearly documented.

**Impact:** Unexpected 429 errors during high-frequency polling.

**Current Limits:**
- Conservative: 5-10 req/s per endpoint
- Monitor for 429 responses and adjust

### 6. SSL Certificate Verification

**Problem:** Self-signed certificates on local Shure devices.

**Impact:** SSL verification failures.

**Solution:**
- Set `MICBOARD_SHURE_API_VERIFY_SSL=false` for local testing
- Use proper CA-signed certificates in production

---

## Docker Demo Configuration

### Quick Start

1. **Create `.env` file in `demo/docker/`:**
   ```bash
   # Required
   MICBOARD_SHURE_API_SHARED_KEY=your_shared_key_here

   # For local Windows Shure System API
   MICBOARD_SHURE_API_BASE_URL=http://host.docker.internal:10000
   MICBOARD_SHURE_API_VERIFY_SSL=false

   # For Georgia Tech VPN
   # MICBOARD_SHURE_API_BASE_URL=http://172.21.x.x:10000
   # MICBOARD_SHURE_API_VERIFY_SSL=true

   # Discovery IPs (comma-separated)
   MICBOARD_DISCOVERY_IPS=172.21.1.100,172.21.1.101,172.21.1.102

   # Polling interval (seconds)
   MICBOARD_POLLING_INTERVAL=60
   ```

2. **Start Docker demo:**
   ```bash
   cd demo/docker
   docker-compose up -d
   ```

3. **Verify connectivity:**
   ```bash
   docker-compose logs micboard-demo | grep "Shure API"
   curl http://localhost:8000/api/health/
   ```

4. **Run device discovery:**
   ```bash
   docker-compose exec micboard-demo python manage.py sync_discovery shure
   docker-compose exec micboard-demo python manage.py poll_devices --manufacturer shure
   ```

5. **Access demo:**
   - Dashboard: http://localhost:8000/
   - API: http://localhost:8000/api/v1/
   - Admin: http://localhost:8000/admin/

### Network Configuration

**For local Windows host:**
```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

**For Georgia Tech VPN (direct network access):**
```yaml
# Uncomment in docker-compose.yml
network_mode: "host"
```

### Testing Checklist

- [ ] Container starts without errors
- [ ] Health check passes (`/api/health/`)
- [ ] Shure API connectivity verified (check logs)
- [ ] Discovery IPs configured correctly
- [ ] Poll devices command runs successfully
- [ ] Devices appear in database
- [ ] WebSocket connections established
- [ ] Dashboard displays devices
- [ ] Add device via discovery works
- [ ] Move device (IP change) works
- [ ] Update device data works
- [ ] Battery alerts trigger correctly
- [ ] Signal quality alerts work
- [ ] Device offline detection works
- [ ] Charger integration works (if applicable)

---

## Next Steps

1. **Create Integration Test Suite** (Task #6)
   - Implement `micboard/tests/test_shure_integration.py`
   - Add mock fixtures for Shure API responses
   - Add live API test mode

2. **Document Troubleshooting** (Task #7)
   - Create `docs/shure-api-troubleshooting.md`
   - Document common errors and solutions
   - Add diagnostic scripts

3. **Validate Docker Demo** (Tasks #8-10)
   - Test all device lifecycle operations
   - Verify business logic functions
   - Create demo walkthrough video/guide

4. **Optimize Performance**
   - Profile polling overhead
   - Implement caching strategies
   - Add metrics/monitoring

---

## References

- [Shure System API Documentation](https://www.shure.com/)
- [Device Lifecycle Refactoring](docs/DEVICE_LIFECYCLE_REFACTORING.md)
- [Network GUID Troubleshooting](docs/SHURE_NETWORK_GUID_TROUBLESHOOTING.md)
- [API Reference](docs/api-reference.md)

---

**Last Updated:** January 22, 2026
**Maintainer:** django-micboard team
