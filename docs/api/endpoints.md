# REST API Endpoints

This section documents the REST API endpoints provided by Django Micboard.

## Data Endpoints

### GET /api/data.json

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

### GET /api/receivers/

List all receivers with summary information.

### GET /api/receivers/{id}/

Get detailed information for a specific receiver.

## Health & Status

### GET /api/health/

Check API and Shure System API health status.

## Device Discovery

### POST /api/discover/

Discover new Shure devices on the network.

### POST /api/refresh/

Force refresh device data from Shure System API.

## Configuration

### GET /api/config/

Get current configuration settings.

### POST /api/config/

Update configuration settings.

## Groups

### PUT /api/groups/{id}/

Update group configuration.

## Error Responses

All endpoints return standard HTTP status codes and JSON error responses:

```json
{
  "error": "Error message",
  "status": 400,
  "details": "Optional detailed information"
}
```

## Rate Limiting

All API endpoints have built-in rate limiting (120 requests per 60 seconds by default).

See the [Rate Limiting Guide](../rate-limiting.md) for details.
