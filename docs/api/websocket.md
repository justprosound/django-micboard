# WebSocket API

Django Micboard provides real-time updates via WebSocket connections.

## Connection

Connect to WebSocket for real-time updates:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/micboard/');

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Received update:', data);
};
```

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

::: micboard.consumers
    options:
      show_signature: true
      show_signature_annotations: true
      show_source: false
      show_labels: true
      show_root_heading: true
      show_category_heading: true
      separate_signature: true
