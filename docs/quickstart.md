# Quick Start Guide

Get django-micboard up and running with your Shure wireless microphone system in minutes.

## Prerequisites

- Python 3.9+
- Django 4.2+ or 5.0+
- A Shure System API server (installed and running)
- Network access to your Shure devices

## Installation

### 1. Install Package

> **CRITICAL POLICY:** All installation and environment management must use [`uv`](https://github.com/astral-sh/uv). Do NOT use pip, venv, or poetry. If you find legacy instructions, escalate immediately. Use `context7` for docs and `gh_grep` for code examples.

```bash
# Create and activate uv virtual environment
uv venv .venv
source .venv/bin/activate

# Install from PyPI
uv pip install django-micboard
```

Or for development:

```bash
uv venv .venv
source .venv/bin/activate

git clone https://github.com/justprosound/django-micboard.git
cd django-micboard
uv pip install -e ".[dev,all]"
```

### 2. Configure Django Settings

Add to your `settings.py`:

```python
INSTALLED_APPS = [
    # ... your other apps
    'channels',
    'micboard',
]

# Shure System API Configuration
MICBOARD_SHURE_API = {
    'BASE_URL': 'https://your-shure-system.local',  # Shure System API URL
    'USERNAME': 'admin',                           # API username
    'PASSWORD': 'your-password',                   # API password
    'VERIFY_SSL': True,                            # Set False for self-signed certs
}

# Django Channels (for WebSocket support)
ASGI_APPLICATION = 'your_project.asgi.application'
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [('127.0.0.1', 6379)],
        },
    },
}
```

### 3. Configure ASGI

Update your `asgi.py`:

```python
import os
import django
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')
django.setup()

from micboard.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': URLRouter(websocket_urlpatterns),
})
```

### 4. Run Migrations

```bash
python manage.py migrate
```

## Shure System Setup

### Enable Shure System API

1. Access your Shure System API management interface
2. Navigate to **Network → API Settings**
3. Enable the **System API**
4. Note the API URL and credentials

### Configure Device Discovery

Add your Shure device IPs to the discovery list:

```bash
# Add discovery IPs
python manage.py add_shure_devices --ips 192.168.1.100 192.168.1.101

# Or configure via admin interface at /admin/micboard/discovery/
```

## Start Monitoring

### Run Device Polling

```bash
# Poll all Shure devices
python manage.py poll_devices --manufacturer shure

# Run continuously (recommended for production)
python manage.py poll_devices --manufacturer shure --continuous
```

### Start Django Server

```bash
python manage.py runserver
```

Visit `http://localhost:8000/admin/` to see your devices!

## Real-time Updates

Django Micboard automatically establishes WebSocket connections for real-time updates:

- Battery levels
- RF signal strength
- Audio levels
- Device status changes

## Next Steps

- Manage assignments and devices in the admin: [guides/admin-interface.md](guides/admin-interface.md)
- Configure monitoring and alerts: [guides/monitoring.md](guides/monitoring.md)
- Enable real-time updates: [guides/realtime-updates.md](guides/realtime-updates.md)
- Explore the API: [api/endpoints.md](api/endpoints.md)

## Troubleshooting

**Can't connect to Shure API?**
- Verify API credentials in settings
- Check network connectivity to Shure system
- Ensure System API is enabled on Shure device

**No devices discovered?**
- Add device IPs to discovery list
- Check device network configuration
- Verify Shure devices are powered on

**WebSocket not working?**
- Install Redis and configure CHANNEL_LAYERS
- Check ASGI configuration
- Verify Django Channels is installed
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application
from micboard.websockets.routing import websocket_urlpatterns

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(websocket_urlpatterns)
    ),
})
```

## 4. Set Up Database

```bash
# Create migrations for micboard models
python manage.py makemigrations micboard

# Apply all migrations
python manage.py migrate
```

### 6. Start Services

Terminal 1 - Django/Daphne:
```bash
daphne -b 0.0.0.0 -p 8000 your_project.asgi:application
```

Terminal 2 - Device Polling:
```bash
python manage.py poll_devices
```

Terminal 3 - Real-Time Subscriptions (Optional):
```bash
# For Shure devices (WebSocket)
python manage.py start_shure_websocket

# For Sennheiser devices (SSE)
python manage.py start_sse_subscriptions
```

Optional: Run the demo instance with Docker (see demo/docker). The demo compose includes the Django app and a minimal database and exposes port 8000. If you run the demo Docker container locally, consider using a restart policy in the compose or a simple watchdog to ensure the Django container is restarted automatically if it crashes.

Example (docker-compose):
```yaml
services:
    micboard-demo:
        restart: unless-stopped
        healthcheck:
            test: ["CMD-SHELL", "curl -f http://localhost:8000/api/health/ || exit 1"]
            interval: 30s
            timeout: 10s
            retries: 5
```

### 7. Access the Dashboard
Open browser to: `http://localhost:8000/micboard/`

Admin Hardware Layout:

In the Django admin you can now access a compact hardware-focused layout at: Admin -> Receivers -> Hardware Layout Overview. This shows per-manufacturer groupings and lists receiver -> channel number -> frequency mappings, making it easy to see channel assignments in the venue.

## Testing the Installation

1. Check API connection:
```bash
curl http://localhost:10000/api/v1/devices
```

2. Discover devices:
```bash
curl -X POST http://localhost:8000/micboard/api/discover/
```

3. Check device data:
```bash
curl http://localhost:8000/micboard/api/data/
```

4. Check real-time connection status:
```bash
python manage.py realtime_status --verbose
```

## Real-Time Features

The system now supports real-time updates via WebSocket (Shure) and SSE (Sennheiser):

- **Automatic Subscription**: Real-time subscriptions start automatically after polling
- **Connection Monitoring**: Use `python manage.py realtime_status` to check connection health
- **Admin Interface**: Monitor connections in Django Admin under "Real-Time Connections"
- **Health Monitoring**: Automatic cleanup of stale connections and error recovery

### Connection States
- `connecting` - Establishing connection
- `connected` - Active real-time updates
- `disconnected` - Temporarily offline
- `error` - Connection failed
- `stopped` - Intentionally stopped

## Troubleshooting

**Problem**: No devices showing
- Check Shure System API is running: `curl http://localhost:10000/api/v1/devices`
- Verify devices are powered on and connected
- Check network connectivity

**Problem**: WebSocket not connecting
- Ensure Daphne is running (not standard Django server)
- Check browser console for errors
- Verify WebSocket URL: `ws://localhost:8000/micboard/ws`

**Problem**: SSL certificate errors
- If using HTTPS with self-signed certificates, disable SSL verification:
  ```python
  MICBOARD_CONFIG = {
      'SHURE_API_VERIFY_SSL': False,  # ⚠️ Only for self-signed certificates
  }
  ```
- For production, use valid SSL certificates and keep verification enabled

**Problem**: Polling not updating
- Check polling service is running
- Look for errors in console output
- Verify API credentials if required

## Next Steps

1. Configure groups in Django Admin
2. Set up systemd services for production
3. Configure Redis for production WebSocket support
4. Customize templates and styling
5. Set up logging and monitoring

## Production Checklist

- [ ] Redis configured for Channels
- [ ] systemd service for polling
- [ ] systemd service for Daphne
- [ ] Nginx/Apache reverse proxy
- [ ] SSL certificates
- [ ] Log rotation
- [ ] Monitoring alerts
- [ ] Backup strategy

For full documentation, see README.md
