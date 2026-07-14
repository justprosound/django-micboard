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
  "receiver_id": 1,
  "data": {
    "channels": [...]
  }
}
```

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
