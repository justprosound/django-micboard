# Shure System API Integration Test Plan

**Version:** 26.01.22
**Date:** January 22, 2026
**Status:** Planning Phase

## Overview

Comprehensive test plan for validating django-micboard's integration with the Shure System API. Covers unit tests, integration tests, end-to-end scenarios, and live API validation.

## Test Categories

### 1. Unit Tests (Mock API Responses)
### 2. Integration Tests (Live API Optional)
### 3. End-to-End Tests (Full Device Lifecycle)
### 4. Performance Tests (Rate Limiting & Load)
### 5. Error Handling Tests (Failure Scenarios)

---

## Test Scenarios Matrix

| Category | Scenario | Priority | Status | Notes |
|----------|----------|----------|--------|-------|
| **Discovery** | Add discovery IPs | HIGH | Not Started | Test add_discovery_ips() |
| **Discovery** | Remove discovery IPs | HIGH | Not Started | Test remove_discovery_ips() |
| **Discovery** | Get discovery IPs | MEDIUM | Not Started | Test get_discovery_ips() |
| **Discovery** | IP conflict detection | HIGH | Not Started | Multiple manufacturers |
| **Devices** | List all devices | HIGH | Not Started | get_devices() |
| **Devices** | Get device details | HIGH | Not Started | get_device(id) |
| **Devices** | Get device channels | HIGH | Not Started | get_device_channels(id) |
| **Devices** | Device identity | MEDIUM | Not Started | get_device_identity(id) |
| **Devices** | Device network info | MEDIUM | Not Started | get_device_network(id) |
| **Devices** | Device status | HIGH | Not Started | get_device_status(id) |
| **Lifecycle** | Add new device | HIGH | Not Started | Discovery → Model creation |
| **Lifecycle** | Move device (IP change) | HIGH | Not Started | Deduplication logic |
| **Lifecycle** | Change device location | MEDIUM | Not Started | Location assignment |
| **Lifecycle** | Device offline detection | HIGH | Not Started | Polling timeout handling |
| **Lifecycle** | Device reconnection | MEDIUM | Not Started | Status update |
| **Polling** | Standard polling cycle | HIGH | Not Started | poll_devices command |
| **Polling** | Polling with errors | HIGH | Not Started | Error recovery |
| **Polling** | Polling rate limiting | MEDIUM | Not Started | Respect API limits |
| **WebSocket** | Connect to WS | MEDIUM | Not Started | WebSocket transport |
| **WebSocket** | Subscribe to device | MEDIUM | Not Started | Device updates |
| **WebSocket** | Handle WS disconnect | LOW | Not Started | Reconnection logic |
| **Auth** | Valid shared key | HIGH | Not Started | Authentication success |
| **Auth** | Invalid shared key | HIGH | Not Started | 401 Unauthorized |
| **Auth** | Missing shared key | HIGH | Not Started | Configuration error |
| **Network** | Connection timeout | HIGH | Not Started | Network unreachable |
| **Network** | SSL verification | MEDIUM | Not Started | Self-signed certs |
| **Network** | Retry on failure | MEDIUM | Not Started | Exponential backoff |
| **Transform** | Device data transform | HIGH | Not Started | Shure → micboard format |
| **Transform** | Transmitter data | HIGH | Not Started | TX data enrichment |
| **Transform** | Channel data | HIGH | Not Started | Channel mapping |
| **Business Logic** | Battery monitoring | MEDIUM | Not Started | Low battery alerts |
| **Business Logic** | Signal quality tracking | MEDIUM | Not Started | RF quality metrics |
| **Business Logic** | Alert creation | LOW | Not Started | Alert rules engine |
| **Business Logic** | Charger integration | LOW | Not Started | Charger slot assignment |

---

## 1. Unit Tests (Mock API Responses)

### 1.1 ShureSystemAPIClient Tests

**File:** `micboard/tests/test_shure_client.py`

```python
class TestShureSystemAPIClient:
    """Test Shure API client with mocked responses."""

    def test_authentication_headers(self):
        """Verify shared key is set correctly in headers."""

    def test_base_url_configuration(self):
        """Test base URL from settings."""

    def test_websocket_url_derivation(self):
        """Test WS URL derived from HTTP base URL."""

    def test_ssl_verification_setting(self):
        """Test SSL verification can be disabled."""

    def test_health_check_success(self, mock_requests):
        """Test health check with valid response."""

    def test_health_check_failure(self, mock_requests):
        """Test health check with 401/500 errors."""

    def test_connection_timeout(self, mock_requests):
        """Test timeout handling."""

    def test_rate_limit_handling(self, mock_requests):
        """Test 429 Too Many Requests response."""
```

### 1.2 ShureDeviceClient Tests

**File:** `micboard/tests/test_shure_device_client.py`

```python
class TestShureDeviceClient:
    """Test device-specific API operations."""

    def test_get_devices_success(self, mock_requests):
        """Test listing all devices."""

    def test_get_device_details(self, mock_requests):
        """Test fetching single device."""

    def test_get_device_channels(self, mock_requests):
        """Test channel data retrieval."""

    def test_get_device_identity(self, mock_requests):
        """Test device identity endpoint."""

    def test_get_device_network(self, mock_requests):
        """Test network info retrieval."""

    def test_get_transmitter_data(self, mock_requests):
        """Test transmitter data for channel."""

    def test_device_not_found(self, mock_requests):
        """Test 404 handling for missing device."""
```

### 1.3 ShureDiscoveryClient Tests

**File:** `micboard/tests/test_shure_discovery_client.py`

```python
class TestShureDiscoveryClient:
    """Test discovery IP management."""

    def test_add_discovery_ips(self, mock_requests):
        """Test adding IPs to discovery list."""

    def test_get_discovery_ips(self, mock_requests):
        """Test retrieving current discovery IPs."""

    def test_remove_discovery_ips(self, mock_requests):
        """Test removing IPs from discovery."""

    def test_add_duplicate_ip(self, mock_requests):
        """Test adding already-present IP."""

    def test_remove_nonexistent_ip(self, mock_requests):
        """Test removing IP not in list."""
```

### 1.4 Data Transformation Tests

**File:** `micboard/tests/test_shure_transformers.py`

```python
class TestShureDataTransformer:
    """Test Shure API data → micboard format."""

    def test_transform_device_data(self):
        """Test device data transformation."""

    def test_transform_transmitter_data(self):
        """Test transmitter data transformation."""

    def test_transform_channel_data(self):
        """Test channel data transformation."""

    def test_handle_missing_fields(self):
        """Test graceful handling of missing API fields."""

    def test_handle_invalid_data(self):
        """Test transformation with malformed data."""
```

---

## 2. Integration Tests (Live API Optional)

### 2.1 Live API Connection Tests

**File:** `micboard/tests/test_shure_integration.py`

```python
@pytest.mark.integration
@pytest.mark.skipif(not LIVE_API_AVAILABLE, reason="No live Shure API")
class TestShureLiveAPIIntegration:
    """Integration tests with live Shure System API.

    Set MICBOARD_SHURE_API_BASE_URL and MICBOARD_SHURE_API_SHARED_KEY
    environment variables to run these tests.
    """

    @pytest.fixture
    def live_client(self):
        """Return configured client for live API."""

    def test_connect_to_live_api(self, live_client):
        """Test connection to live Shure API."""

    def test_list_live_devices(self, live_client):
        """Test listing devices from live API."""

    def test_fetch_device_details(self, live_client):
        """Test fetching details for known device."""

    def test_discovery_ip_roundtrip(self, live_client):
        """Test add → get → remove discovery IP cycle."""
```

### 2.2 Service Layer Integration Tests

**File:** `micboard/tests/test_shure_services_integration.py`

```python
class TestShureServicesIntegration:
    """Test service layer with Shure plugin."""

    def test_polling_service_with_shure(self, mock_shure_api):
        """Test PollingService.poll_manufacturer() with Shure."""

    def test_discovery_service_with_shure(self, mock_shure_api):
        """Test DiscoveryService with Shure plugin."""

    def test_device_lifecycle_service(self, mock_shure_api):
        """Test DeviceLifecycleManager with Shure devices."""

    def test_manufacturer_service_health(self, mock_shure_api):
        """Test ManufacturerService health checks."""
```

---

## 3. End-to-End Tests (Full Device Lifecycle)

### 3.1 Device Add Flow

**Scenario:** Discover and add a new device

```python
def test_e2e_device_add_flow(self):
    """Test complete flow: discovery → API fetch → model creation → broadcast.

    Steps:
    1. Add IP to discovery list
    2. Wait for Shure API to detect device
    3. Poll devices via PollingService
    4. Verify Receiver model created
    5. Verify WebSocket broadcast sent
    6. Verify device appears in API responses
    """
```

### 3.2 Device Move Flow

**Scenario:** Existing device changes IP address

```python
def test_e2e_device_move_flow(self):
    """Test device IP change (move scenario).

    Steps:
    1. Device exists with IP 172.21.1.100
    2. Device changes to IP 172.21.1.101
    3. Poll detects duplicate via serial/MAC
    4. Deduplication logic updates IP
    5. Old IP removed, new IP associated
    6. Location preserved
    7. WebSocket broadcast sent
    """
```

### 3.3 Device Change Flow

**Scenario:** Device location/assignment changes

```python
def test_e2e_device_change_flow(self):
    """Test device metadata updates.

    Steps:
    1. Update device location
    2. Update user assignment
    3. Verify database state
    4. Verify WebSocket broadcast
    5. Verify API reflects changes
    """
```

### 3.4 Device Offline Detection

**Scenario:** Device becomes unreachable

```python
def test_e2e_device_offline_flow(self):
    """Test offline device detection.

    Steps:
    1. Device initially online
    2. Device stops responding to polls
    3. Timeout threshold exceeded
    4. Device marked offline (is_active=False)
    5. Alert created (if configured)
    6. WebSocket broadcast sent
    """
```

---

## 4. Performance Tests

### 4.1 Rate Limiting Tests

```python
def test_rate_limit_compliance(self):
    """Verify we respect Shure API rate limits.

    - Device list: 5 req/s
    - Device details: 10 req/s
    - Verify no 429 errors during normal polling
    """

def test_concurrent_requests(self):
    """Test multiple simultaneous API calls."""

def test_polling_performance(self):
    """Test polling cycle completes within time budget."""
```

### 4.2 Load Tests

```python
def test_many_devices_polling(self):
    """Test polling with 50+ devices."""

def test_websocket_under_load(self):
    """Test WebSocket with many concurrent updates."""
```

---

## 5. Error Handling Tests

### 5.1 Network Errors

```python
def test_connection_refused(self):
    """Test API server unreachable."""

def test_dns_resolution_failure(self):
    """Test invalid hostname."""

def test_ssl_certificate_error(self):
    """Test SSL verification failure."""

def test_timeout_handling(self):
    """Test request timeout recovery."""
```

### 5.2 API Errors

```python
def test_401_unauthorized(self):
    """Test invalid/missing shared key."""

def test_404_not_found(self):
    """Test device not found."""

def test_429_rate_limit(self):
    """Test rate limit exceeded."""

def test_500_server_error(self):
    """Test Shure API internal error."""

def test_503_service_unavailable(self):
    """Test Shure API down/restarting."""
```

### 5.3 Data Errors

```python
def test_malformed_json_response(self):
    """Test invalid JSON from API."""

def test_missing_required_fields(self):
    """Test response missing expected fields."""

def test_invalid_device_data(self):
    """Test transformation with bad data."""
```

---

## Test Implementation Priority

### Phase 1: Foundation (Week 1)
- [x] Test file structure setup
- [ ] Mock fixtures for API responses
- [ ] Basic client unit tests
- [ ] Transformation unit tests

### Phase 2: Integration (Week 2)
- [ ] Service layer integration tests
- [ ] Plugin integration tests
- [ ] Live API connection tests (optional)

### Phase 3: End-to-End (Week 3)
- [ ] Device add flow
- [ ] Device move flow
- [ ] Offline detection
- [ ] Location/assignment changes

### Phase 4: Robustness (Week 4)
- [ ] Error handling tests
- [ ] Performance tests
- [ ] Rate limiting validation
- [ ] Load testing

---

## Test Data Fixtures

### Mock Device Response

```python
MOCK_SHURE_DEVICE = {
    "device_id": "00:0e:dd:4c:43:78",
    "model": "ULXD4D",
    "serial_number": "08A0D01234",
    "ip_address": "172.21.1.100",
    "firmware_version": "2.7.6.0",
    "status": "online",
    "channels": [
        {
            "channel_number": 1,
            "frequency": "584.000",
            "audio_level": -45,
            "rf_level": 85
        }
    ]
}
```

### Mock Discovery IPs Response

```python
MOCK_DISCOVERY_IPS = {
    "ips": ["172.21.1.100", "172.21.1.101", "172.21.1.102"]
}
```

---

## CI/CD Integration

### GitHub Actions Workflow

```yaml
name: Shure Integration Tests

on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run unit tests
        run: pytest -m "not integration" micboard/tests/test_shure_*.py

  integration-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v2
      - name: Run integration tests
        run: pytest -m integration micboard/tests/test_shure_integration.py
        env:
          MICBOARD_SHURE_API_BASE_URL: ${{ secrets.SHURE_API_URL }}
          MICBOARD_SHURE_API_SHARED_KEY: ${{ secrets.SHURE_API_KEY }}
```

---

## Test Environment Setup

### Local Development

```bash
# 1. Create test database
./manage.py migrate --settings=demo.settings

# 2. Set environment variables
export MICBOARD_SHURE_API_BASE_URL=http://localhost:8080
export MICBOARD_SHURE_API_SHARED_KEY=test_key

# 3. Run unit tests only
pytest -m "not integration" micboard/tests/test_shure_*.py

# 4. Run with live API
pytest -m integration micboard/tests/test_shure_integration.py
```

### Docker Test Environment

```bash
# Use demo/docker setup with local Shure API
cd demo/docker
docker-compose up -d
docker-compose exec web pytest micboard/tests/test_shure_*.py
```

---

## Success Criteria

### Test Coverage Goals
- **Unit tests:** 90%+ coverage
- **Integration tests:** Core flows covered
- **E2E tests:** All 4 lifecycle scenarios pass
- **Error handling:** All failure modes tested

### Performance Goals
- Polling cycle: <10s for 20 devices
- API response time: <500ms average
- Rate limits: 0 violations
- WebSocket latency: <100ms

### Reliability Goals
- Zero unhandled exceptions
- Graceful degradation on API errors
- Auto-recovery from network issues
- No data loss on failures

---

## Test Maintenance

### Review Schedule
- Weekly: Review failing tests
- Monthly: Update mock data to match API changes
- Quarterly: Validate against live API
- Release: Full test suite before deployment

### Documentation
- Keep test docstrings updated
- Document breaking API changes
- Maintain fixture data accuracy
- Update test plan with new scenarios

---

**Status:** Ready for implementation
**Next Step:** Create `test_shure_client.py` with basic unit tests
**Estimated Effort:** 4-6 weeks for complete coverage
