# Real-time Updates

Django Micboard provides real-time monitoring of Shure wireless microphone systems through WebSocket connections and automatic data synchronization.

## WebSocket Architecture

### Connection Overview

```
Shure System API → Django Micboard → WebSocket → Frontend
       ↑                    ↓              ↓
   Device Polling    Database Updates   Live Updates
```

### WebSocket Endpoints

- **Device Updates**: `ws://your-server/ws/devices/`
- **Connection Status**: `ws://your-server/ws/connections/`
- **System Health**: `ws://your-server/ws/health/`

## Real-time Data Types

### Device Metrics

**Battery Information:**
```json
{
  "type": "device_update",
  "device_id": "SHURE001",
  "battery_level": 85,
  "charging": false,
  "battery_status": "good"
}
```

**RF Signal Data:**
```json
{
  "type": "device_update",
  "device_id": "SHURE001",
  "rf_signal": -45,
  "rf_quality": "excellent",
  "interference": false
}
```

**Audio Levels:**
```json
{
  "type": "device_update",
  "device_id": "SHURE001",
  "audio_level": -12,
  "peak_level": -6,
  "mute_status": false
}
```

### Connection Status

**WebSocket Connection Health:**
```json
{
  "type": "connection_update",
  "manufacturer": "shure",
  "status": "connected",
  "latency_ms": 45,
  "last_update": "2024-01-22T10:30:00Z"
}
```

**API Connection Status:**
```json
{
  "type": "api_health",
  "endpoint": "https://shure-system.local",
  "status": "healthy",
  "response_time_ms": 234,
  "error_count": 0
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
        this.ws = new WebSocket('ws://your-server/ws/devices/');

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
        const ws = new WebSocket('ws://your-server/ws/devices/');

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
from channels.routing import ProtocolTypeRouter, URLRouter
from micboard.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': URLRouter(websocket_urlpatterns),
})
```

### WebSocket Consumers

```python
# micboard/consumers.py
from channels.generic.websocket import JsonWebsocketConsumer
from micboard.services import DeviceService

class DeviceConsumer(JsonWebsocketConsumer):
    def connect(self):
        self.accept()
        # Send initial device data
        devices = DeviceService.get_all_devices()
        self.send_json({
            'type': 'initial_data',
            'devices': devices
        })

    def disconnect(self, close_code):
        pass

    def device_update(self, event):
        # Send device update to WebSocket
        self.send_json(event['data'])
```

## Data Synchronization

### Polling Strategy

**Continuous Polling:**
```bash
# Poll every 30 seconds
python manage.py poll_devices --manufacturer shure --continuous --interval 30
```

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
