# Real-time Updates

Django Micboard provides real-time monitoring of Shure wireless microphone systems through WebSocket connections and automatic data synchronization.

## WebSocket Architecture

### Connection Overview

```
Shure System API → Django Micboard → WebSocket → Frontend
       ↑                    ↓              ↓
   Device Polling    Database Updates   Live Updates
```

### WebSocket Endpoint

Device, connection, alert, and system-health events share the authenticated `/ws` endpoint.

## Real-time Data Types

### Bounded device projections

Polling and discovery publish persisted chassis projections in bounded, resumable batches:

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
    "snapshot_id": "shared-across-resumed-batches",
    "chunk_index": 0,
    "is_final_chunk": true,
    "inventory_complete": false,
    "next_cursor": 42,
    "broadcast_namespace": "poll"
  }
}
```

`is_final_chunk` ends the current invocation's chunk sequence; only `inventory_complete` ends the
full projection. Preserve rows by `snapshot_id` across invocations until that flag is true.

### Connection Status

**Persisted device status:**
```json
{
  "type": "device_status_update",
  "service_code": "shure",
  "device_id": 1,
  "device_type": "WirelessChassis",
  "status": "online",
  "is_active": true
}
```

**API Connection Status:**
```json
{
  "type": "api_health_update",
  "manufacturer_code": "shure",
  "health_data": {
    "status": "healthy",
    "response_time": 0.234
  }
}
```

## Frontend Integration

### JavaScript WebSocket Client

```javascript
class MicboardWebSocket {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
    }

    connect() {
        this.ws = new WebSocket('ws://your-server/ws');

        this.ws.onopen = () => {
            console.log('Connected to Micboard WebSocket');
            this.reconnectAttempts = 0;
        };

        this.ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleMessage(data);
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            this.attemptReconnect();
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    handleMessage(data) {
        switch(data.type) {
            case 'device_update':
                this.updateDeviceDisplay(data);
                break;
            case 'connection_update':
                this.updateConnectionStatus(data);
                break;
            case 'system_alert':
                this.showAlert(data);
                break;
        }
    }

    updateDeviceDisplay(data) {
        const deviceElement = document.getElementById(`device-${data.device_id}`);
        if (deviceElement) {
            // Update battery level
            const batteryBar = deviceElement.querySelector('.battery-bar');
            batteryBar.style.width = `${data.battery_level}%`;

            // Update signal strength
            const signalIcon = deviceElement.querySelector('.signal-icon');
            signalIcon.className = `signal-icon ${data.rf_quality}`;

            // Update timestamp
            const timestamp = deviceElement.querySelector('.last-update');
            timestamp.textContent = new Date().toLocaleTimeString();
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);

            setTimeout(() => {
                console.log(`Attempting WebSocket reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
                this.connect();
            }, delay);
        }
    }
}

// Initialize
const micboardWS = new MicboardWebSocket();
micboardWS.connect();
```

### React Component Example

```jsx
import React, { useEffect, useState } from 'react';

function DeviceMonitor({ deviceId }) {
    const [deviceData, setDeviceData] = useState(null);
    const [connectionStatus, setConnectionStatus] = useState('disconnected');

    useEffect(() => {
        const ws = new WebSocket('ws://your-server/ws');

        ws.onopen = () => setConnectionStatus('connected');

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.device_id === deviceId) {
                setDeviceData(data);
            }
        };

        ws.onclose = () => setConnectionStatus('disconnected');

        return () => ws.close();
    }, [deviceId]);

    if (!deviceData) return <div>Loading...</div>;

    return (
        <div className="device-monitor">
            <h3>{deviceData.name}</h3>
            <div className="metrics">
                <div className="battery">
                    Battery: {deviceData.battery_level}%
                    <div className="battery-bar" style={{width: `${deviceData.battery_level}%`}} />
                </div>
                <div className="signal">
                    RF: {deviceData.rf_signal} dBm ({deviceData.rf_quality})
                </div>
                <div className="audio">
                    Audio: {deviceData.audio_level} dB
                </div>
            </div>
            <div className="status">
                Status: {connectionStatus}
            </div>
        </div>
    );
}
```

## Backend Configuration

### Django Channels Setup

**settings.py:**
```python
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [('127.0.0.1', 6379)],
        },
    },
}
```

**asgi.py:**
```python
import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "your_project.settings")
django_asgi_app = get_asgi_application()

from micboard.websockets.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
    ),
})
```

### Running subscription supervisors

Subscription supervisors are explicit long-running processes. Polling never starts or enqueues a
supervisor. The management commands run in the foreground until the subscriptions end or the
process is interrupted, so run them under your normal process supervisor:

```bash
# Shure WebSocket supervisor
uv run --no-sync python manage.py websocket_subscribe

# Sennheiser SSE supervisor
uv run --no-sync python manage.py sse_subscribe --manufacturer sennheiser

# Optional single-device diagnostic selection
uv run --no-sync python manage.py sse_subscribe \
  --manufacturer sennheiser --device DEVICE_ID
```

For queue-managed deployments, Micboard registers
`start_shure_websocket_subscriptions` and `start_sse_subscriptions` as native Huey task
entrypoints. The host deployment or scheduler must explicitly enqueue the appropriate entrypoint
once; recurring device polls do not do so. These long-running tasks consume a Huey worker slot,
so reserve worker capacity accordingly.

Every command and Huey entrypoint uses the same renewable singleton lease. A deployment with more
than one process must point `MICBOARD_REALTIME_CACHE_ALIAS` (default: `"default"`) at a
process-shared Django cache. A local-memory cache only deduplicates inside one process. The
following settings bound each supervisor:

- `MICBOARD_REALTIME_MAX_DEVICES`: 64 by default, hard-capped at 256.
- `MICBOARD_REALTIME_MAX_CONCURRENCY`: 16 by default, hard-capped at 64 and never greater than the
  device limit.
- `MICBOARD_REALTIME_ROTATION_SECONDS`: 300 by default, hard-capped at 3,600. A long-lived
  connection is cancelled after its turn so a fixed worker cannot starve later selected devices.
- `MICBOARD_REALTIME_RECONNECT_DELAY_SECONDS`: 1 by default, hard-capped at 60. This pause applies
  between repeated connection rounds.

Each supervisor uses at most the configured concurrency count of worker tasks. Inventory selection
uses a shared-cache circular primary-key cursor. Each completed connection round reloads the next
bounded window under the same lease, and restarts resume from the persisted cursor. Point the cache
alias at process-shared storage to preserve this fairness across workers. Explicit single-device
diagnostics do not advance that cursor.

The lease is renewed every 15 seconds. After a crash or clean stop, wait up to 60 seconds before
restarting the same transport. Micboard deliberately lets the token expire because Django's
generic cache API cannot safely compare and delete a lease owned by a particular process.

### Initial Hardware Queries

The bundled `MicboardConsumer` handles authenticated WebSocket updates. Use the user-scoped
manager when a view needs an initial snapshot:

```python
from micboard.models.hardware.wireless_chassis import WirelessChassis

chassis = WirelessChassis.objects.for_user(user=request.user).active()
snapshot = list(chassis.values("id", "name", "status"))
```

## Data Synchronization

### Polling Strategy

**Queued Polling:**
```bash
# Enqueue one poll through native Huey
uv run --no-sync python manage.py poll_devices --manufacturer shure --async
```

Use your deployment scheduler to enqueue this one-shot command at the required interval.

Polling and realtime subscriptions have separate lifecycles. Increasing the poll frequency does
not create, restart, or reconcile subscription supervisors.

**Adaptive Polling:**
- Normal devices: 30-second intervals
- Critical devices: 10-second intervals
- Offline devices: 60-second intervals

### Change Detection

**Efficient Updates:**
- Only send changed data
- Use ETags for API polling
- Implement diff-based updates

```python
def send_device_update(device, changes):
    # Only send changed fields
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        'devices',
        {
            'type': 'device_update',
            'data': {
                'device_id': device.device_id,
                'changes': changes,
                'timestamp': timezone.now().isoformat()
            }
        }
    )
```

## Performance Optimization

### Connection Pooling

**Redis Configuration:**
```python
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [('127.0.0.1', 6379)],
            'capacity': 1000,  # Connection pool size
            'expiry': 300,     # Connection expiry
        },
    },
}
```

### Message Batching

**Batch Updates:**
```python
def batch_device_updates(updates):
    # Group updates by time window
    batches = group_updates_by_time(updates, window_seconds=1)

    for batch in batches:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'devices',
            {
                'type': 'batch_update',
                'updates': batch
            }
        )
```

### Client-side Optimization

**Update Throttling:**
```javascript
class UpdateThrottler {
    constructor(delay = 100) {
        this.delay = delay;
        this.timeout = null;
        this.pendingUpdates = {};
    }

    queueUpdate(deviceId, update) {
        this.pendingUpdates[deviceId] = update;

        if (this.timeout) clearTimeout(this.timeout);

        this.timeout = setTimeout(() => {
            this.flushUpdates();
        }, this.delay);
    }

    flushUpdates() {
        // Send batched updates
        Object.entries(this.pendingUpdates).forEach(([deviceId, update]) => {
            this.applyUpdate(deviceId, update);
        });
        this.pendingUpdates = {};
    }
}
```

## Monitoring and Debugging

### WebSocket Debugging

**Browser Developer Tools:**
- Network tab: WebSocket connections
- Console: Connection events and messages
- Application tab: WebSocket frames

**Django Debug Toolbar:**
```python
# settings.py
INSTALLED_APPS += ['debug_toolbar']
MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
```

### Connection Health Monitoring

**Health Checks:**
```python
from channels.layers import get_channel_layer

def check_websocket_health():
    channel_layer = get_channel_layer()

    # Test channel layer connectivity
    try:
        async_to_sync(channel_layer.send)('health_check', {'ping': True})
        return True
    except Exception as e:
        logger.error(f"WebSocket health check failed: {e}")
        return False
```

## Troubleshooting

### Connection Issues

**WebSocket won't connect:**
- Check ASGI configuration
- Verify Redis is running
- Confirm firewall settings
- Check SSL certificate validity

**Updates not received:**
- Verify channel layer configuration
- Check consumer group subscriptions
- Monitor Redis connection pool
- Review message serialization

### Performance Issues

**High latency:**
- Optimize database queries
- Implement message caching
- Use connection pooling
- Monitor Redis performance

**Memory usage:**
- Implement message cleanup
- Use efficient serialization
- Monitor connection counts
- Configure appropriate timeouts

### Common Patterns

**Heartbeat Implementation:**
```javascript
// Client heartbeat
setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({type: 'ping'}));
    }
}, 30000);

// Server heartbeat response
def receive(self, text_data):
    data = json.loads(text_data)
    if data.get('type') == 'ping':
        self.send_json({'type': 'pong'})
```

**Reconnection Logic:**
```javascript
class ReconnectingWebSocket {
    constructor(url, options = {}) {
        this.url = url;
        this.options = {
            maxReconnectAttempts: 5,
            reconnectInterval: 1000,
            maxReconnectInterval: 30000,
            ...options
        };
        this.reconnectAttempts = 0;
        this.connect();
    }

    connect() {
        this.ws = new WebSocket(this.url);
        // ... connection handlers
    }

    handleClose() {
        if (this.reconnectAttempts < this.options.maxReconnectAttempts) {
            const delay = Math.min(
                this.options.reconnectInterval * Math.pow(2, this.reconnectAttempts),
                this.options.maxReconnectInterval
            );

            setTimeout(() => {
                this.reconnectAttempts++;
                this.connect();
            }, delay);
        }
    }
}
```
