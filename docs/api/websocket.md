# WebSocket API

Django Micboard provides real-time updates via WebSocket connections.

## Connection

Connect to WebSocket for real-time updates:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Received update:', data);
};
```

## Authorization and routing

Every connection must be authenticated. Authorization then depends on deployment mode:

- In single-site, non-MSP mode, the user must have Django permission
  `micboard.view_realtimeconnection` to join the global update stream.
- In MSP mode, the user joins only groups derived from active organization/campus memberships.
  Users without an active, internally consistent membership are rejected; superusers receive no
  global bypass.
- In multi-site mode, the authenticated user joins only the group for the current Django
  `SITE_ID`. When MSP and multi-site modes are both enabled, memberships are additionally limited
  to organizations on that site.

Unauthenticated clients close with code `4401`; authenticated but unauthorized clients close with
code `4403`. These browser subscriptions are separate from backend-to-hardware SSE or manufacturer
WebSocket transports.

## Message Types

### Device Update

```json
{
  "type": "device_update",
  "data": {
    "manufacturer_code": "shure",
    "receivers": [
      {
        "id": 1,
        "api_device_id": "receiver-1",
        "name": "Stage receiver",
        "ip": "192.0.2.10",
        "status": "online",
        "model": "ULXD4Q"
      }
    ],
    "timestamp": "2026-07-14T12:00:00+00:00",
    "snapshot_id": "shared-across-resumed-batches",
    "chunk_index": 0,
    "is_final_chunk": true,
    "inventory_complete": false,
    "next_cursor": 42,
    "broadcast_namespace": "poll"
  }
}
```

`is_final_chunk` marks the last Channels message in the current invocation.
`inventory_complete` marks the end of the full manufacturer projection. When it is false, a later
poll or discovery run resumes after `next_cursor` with the same `snapshot_id`. Clients should not
treat a partial batch as a complete fleet replacement. Device and chunk counts are bounded by
`MICBOARD_POLL_MAX_DEVICES` and `MICBOARD_POLL_BROADCAST_CHUNK_SIZE`.

### Alert
```json
{
  "type": "alert",
  "severity": "warning",
  "message": "Low battery on Wireless Mic 1",
  "channel_id": 5
}
```

### Status
```json
{
  "type": "status",
  "message": "Connected to Shure System API"
}
```

## Python WebSocket Consumer

::: micboard.websockets.consumers
    options:
      show_signature: true
      show_signature_annotations: true
      show_source: false
      show_labels: true
      show_root_heading: true
      show_category_heading: true
      separate_signature: true
