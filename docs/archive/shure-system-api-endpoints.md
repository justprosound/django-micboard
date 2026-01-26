# Shure System API - Endpoint Reference

**Base URL**: `https://localhost:10000` (default installation)
**Authentication**: Bearer token + x-api-key header (shared key from installation)
**API Version**: v1

## Authentication

All requests require authentication headers:

```bash
Authorization: Bearer {shared_key}
x-api-key: {shared_key}
```

Shared key location (Windows): `C:\ProgramData\Shure\SystemAPI\Standalone\Security\sharedkey.txt`

## Core Endpoints

### Devices

#### List All Devices
```http
GET /api/v1/devices
```

Returns array of device objects discovered by the System API.

**Response** (200 OK):
```json
[
  {
    "id": "device-uuid",
    "model": "ULXD4Q",
    "ipAddress": "172.21.1.100",
    "name": "Receiver 1",
    "firmware": "2.7.14",
    "channels": 4
  }
]
```

**Empty State**: Returns `[]` when no devices discovered

#### Get Device Details
```http
GET /api/v1/devices/{device_id}
```

Returns detailed information for a specific device.

**Response** (200 OK):
```json
{
  "id": "device-uuid",
  "model": "ULXD4Q",
  "ipAddress": "172.21.1.100",
  "name": "Receiver 1",
  "firmware": "2.7.14",
  "serialNumber": "ABC123",
  "channels": 4
}
```

#### Get Device Channels
```http
GET /api/v1/devices/{device_id}/channels
```

Returns channel/transmitter information for a device.

**Response** (200 OK):
```json
[
  {
    "channel": 1,
    "frequency": "542.000",
    "transmitter": {
      "model": "ULXD2",
      "battery": 85,
      "rssi": -45
    }
  }
]
```

#### Get Channel Transmitter
```http
GET /api/v1/devices/{device_id}/channels/{channel}/tx
```

Returns transmitter details for a specific channel.

#### Get Device Identity
```http
GET /api/v1/devices/{device_id}/identify
```

Returns identity information (serial number, model variant, firmware).

#### Get Device Network
```http
GET /api/v1/devices/{device_id}/network
```

Returns network information (hostname, MAC address).

#### Get Device Status
```http
GET /api/v1/devices/{device_id}/status
```

Returns operational status (frequency band, location).

#### Get Supported Models
```http
GET /api/v1/devices/models
```

Returns list of device models supported by this System API version.

**Response** (200 OK):
```json
["ULXD4", "ULXD4Q", "ULXD4D", "AD4Q", "ULXD6"]
```

### Discovery Configuration

The Shure System API discovers devices by polling IP addresses in its discovery list.
Django Micboard pushes IPs to this list for discovery.

#### Get Discovery IPs
```http
GET /api/v1/config/discovery/ips
```

Returns the list of IP addresses being polled for device discovery.

**Response** (200 OK):
```json
{
  "ips": [
    "172.21.1.100",
    "172.21.1.101",
    "172.21.1.102"
  ]
}
```

#### Add/Replace Discovery IPs
```http
PUT /api/v1/config/discovery/ips
```

Replaces the entire discovery IP list (not additive - use GET first to preserve existing).

**Request Body**:
```json
{
  "ips": [
    "172.21.1.100",
    "172.21.1.101",
    "172.21.1.102",
    "172.21.1.103"
  ]
}
```

**Response** (202 Accepted):
```json
{
  "status": "accepted",
  "message": "Discovery IPs updated"
}
```

**Implementation Pattern** (for adding IPs without removing existing):
```python
# 1. GET existing IPs
existing = requests.get("/api/v1/config/discovery/ips").json()["ips"]

# 2. Merge with new IPs (deduplicate)
new_ips = ["172.21.1.104", "172.21.1.105"]
combined = list(dict.fromkeys(existing + new_ips))

# 3. PUT merged list
requests.put("/api/v1/config/discovery/ips", json={"ips": combined})
```

#### Remove Discovery IPs
```http
PATCH /api/v1/config/discovery/ips/remove
POST /api/v1/config/discovery/ips/remove
```

Removes specific IPs from discovery list (PATCH preferred, POST fallback).

**Request Body**:
```json
{
  "ips": [
    "172.21.1.102"
  ]
}
```

**Response** (200 OK):
```json
{
  "status": "removed",
  "count": 1
}
```

### System Information

#### Get System Info
```http
GET /api/v1/system/info
```

Returns System API version and capabilities.

**Response** (200 OK):
```json
{
  "version": "1.0.0",
  "apiVersion": "v1",
  "capabilities": ["discovery", "devices", "subscriptions"]
}
```

### WebSocket Subscriptions

#### Create WebSocket Connection
```http
WS /api/v1/subscriptions/websocket/create
```

Establishes WebSocket connection for real-time device updates.

**Protocol**: WebSocket (ws:// or wss://)
**Authentication**: Via query param or header

**Subscription Message**:
```json
{
  "action": "subscribe",
  "deviceId": "device-uuid"
}
```

**Update Message** (received):
```json
{
  "type": "device_update",
  "deviceId": "device-uuid",
  "data": {
    "channel": 1,
    "battery": 84,
    "rssi": -46
  }
}
```

## Error Responses

### 401 Unauthorized
```json
{
  "error": "Unauthorized",
  "message": "Invalid or missing API key"
}
```

### 404 Not Found
```json
{
  "error": "Not Found",
  "message": "Device not found",
  "statusCode": 404
}
```

### 429 Too Many Requests
```json
{
  "error": "Rate limit exceeded",
  "retry_after": 30
}
```

Headers:
```
Retry-After: 30
```

### 500 Internal Server Error
```json
{
  "error": "Internal Server Error",
  "message": "System API encountered an error"
}
```

## Usage Patterns

### Discovery Flow

1. **Add IPs to discovery list** (Django → Shure API):
   ```python
   # GET existing + PUT merged
   existing = client.get("/api/v1/config/discovery/ips")["ips"]
   new_list = existing + ["172.21.1.104"]
   client.put("/api/v1/config/discovery/ips", {"ips": new_list})
   ```

2. **Shure API polls IPs** (automatic background process)

3. **Django polls for devices** (periodic task):
   ```python
   devices = client.get("/api/v1/devices")
   for device in devices:
       # Create/update Receiver in Django
   ```

### Polling Flow

1. **List devices**:
   ```python
   devices = client.get("/api/v1/devices")
   ```

2. **Get detailed data** (per device):
   ```python
   for device in devices:
       details = client.get(f"/api/v1/devices/{device['id']}")
       channels = client.get(f"/api/v1/devices/{device['id']}/channels")
       # Optional enrichment
       identity = client.get(f"/api/v1/devices/{device['id']}/identify")
       network = client.get(f"/api/v1/devices/{device['id']}/network")
   ```

3. **Transform and save**:
   ```python
   # Convert Shure format → Django models
   Receiver.objects.update_or_create(
       api_device_id=device['id'],
       defaults={'ip': device['ipAddress'], 'name': device['name']}
   )
   ```

## Rate Limiting

The Shure System API has built-in rate limiting. Django Micboard implements client-side rate limiting:

- **Device list**: 5 req/sec
- **Device details**: 10 req/sec
- **Channel data**: 10 req/sec
- **Discovery config**: 1 req/sec

## Configuration in Django

```python
# demo/settings.py or .env
MICBOARD_CONFIG = {
    'SHURE_API_BASE_URL': 'https://localhost:10000',
    'SHURE_API_SHARED_KEY': '<from sharedkey.txt>',
    'SHURE_API_VERIFY_SSL': False,  # For self-signed cert
    'SHURE_API_TIMEOUT': 10,
    'SHURE_API_MAX_RETRIES': 3,
}
```

## Notes

- **No Health Endpoint**: Use `/api/v1/devices` as health check
- **No UI**: All operations via API only
- **Discovery is polling-based**: Not real-time device detection
- **WebSocket for real-time**: Use subscriptions for live updates
- **SSL Certificate**: Self-signed by default, set verify=False in client
