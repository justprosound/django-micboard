# Quick Start Guide

Get django-micboard up and running with your Shure wireless microphone system in minutes.

## Prerequisites

- Python 3.13+
- Django 5.1 through 6.0
- A Shure System API server (installed and running)
- Network access to your Shure devices

## Installation

### 1. Install Package

Add django-micboard and the optional real-time dependencies to your uv-managed host project:

```bash
uv add "django-micboard[standard,realtime,shure]"
```

Or for development:

```bash
git clone https://github.com/justprosound/django-micboard.git
cd django-micboard
uv sync --locked --all-extras
```

### 2. Configure Django Settings

Add to your `settings.py`:

```python
import os

DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"

INSTALLED_APPS = [
    # ... your other apps
    "channels",
    "huey.contrib.djhuey",
    "micboard",
]

MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": "https://your-shure-system.local:10000",
    "SHURE_API_SHARED_KEY": os.environ.get("MICBOARD_SHURE_API_SHARED_KEY"),
}

MICBOARD_API_SERVER_ALLOWED_HOSTS = ["your-shure-system.local"]

HUEY = {
    "huey_class": "huey.RedisHuey",
    "name": "micboard",
    "connection": {"url": os.environ.get("REDIS_URL", "redis://localhost:6379/1")},
    "immediate": DEBUG,
}

# Django Channels (for WebSocket support)
ASGI_APPLICATION = "your_project.asgi.application"
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],
        },
    },
}
```

### 3. Configure ASGI

Update your `asgi.py`:

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

### 4. Run Migrations

```bash
uv run --no-sync python manage.py migrate
```

## Shure System Setup

### Enable Shure System API

1. Access your Shure System API management interface
2. Navigate to **Network → API Settings**
3. Enable the **System API**
4. Note the API URL and shared key

### Configure Device Discovery

Add your Shure device IPs to the discovery list:

```bash
# Add discovery IPs
uv run --no-sync python manage.py discovery_add_devices --ips 192.168.1.100,192.168.1.101

# Or configure candidates at /admin/micboard/discovereddevice/
```

## Start Monitoring

### Run Device Polling

```bash
# Poll all Shure devices
uv run --no-sync python manage.py poll_devices --manufacturer shure

# Enqueue one poll through native Huey
uv run --no-sync python manage.py poll_devices --manufacturer shure --async

# Run the native Huey consumer outside immediate/development mode
uv run --no-sync python manage.py run_huey
```

### Start Django Server

```bash
uv run --no-sync python manage.py runserver
```

Visit `http://localhost:8000/admin/` to see your devices!

## Real-time Updates

Polling and subscription tasks feed real-time updates for:

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

## Testing the Installation

1. Check Django configuration:
```bash
uv run --no-sync python manage.py check
```

2. Sign in to Django admin and inspect the registered Micboard models.

3. Check real-time connection status:
```bash
uv run --no-sync python manage.py realtime_status --verbose
```

## Real-Time Features

The system now supports real-time updates via WebSocket (Shure) and SSE (Sennheiser):

- **Explicit Subscription**: Run `websocket_subscribe` or `sse_subscribe` as a foreground process,
  or explicitly enqueue its registered native Huey entrypoint
- **Independent Polling**: Queued polling never starts or multiplies subscription supervisors
- **Singleton Safety**: Multi-process deployments use a shared Django cache lease; restart after a
  stop or crash can take up to 60 seconds
- **Connection Monitoring**: Use `uv run --no-sync python manage.py realtime_status` to check connection health
- **Admin Interface**: Monitor connections in Django Admin under "Real-Time Connections"
- **Health Monitoring**: Automatic cleanup of stale connections and error recovery

```bash
uv run --no-sync python manage.py websocket_subscribe
uv run --no-sync python manage.py sse_subscribe --manufacturer sennheiser
```

### Connection States
- `connecting` - Establishing connection
- `connected` - Active real-time updates
- `disconnected` - Temporarily offline
- `error` - Connection failed
- `stopped` - Intentionally stopped

## Troubleshooting

**Problem**: No devices showing
- Run `uv run --no-sync python manage.py diagnostic_api_health_check`
- Verify devices are powered on and connected
- Check network connectivity

**Problem**: WebSocket not connecting
- Ensure an ASGI server is running in production
- Check browser console for errors
- Verify WebSocket URL: `ws://localhost:8000/ws`

**Problem**: SSL certificate errors
- Install the issuing CA in the host trust store, or set `SSL_CERT_FILE`/`SSL_CERT_DIR` for the
  Django and Huey processes. Certificate verification cannot be disabled.

**Problem**: Polling not updating
- Check the Huey consumer and deployment scheduler are running
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
- [ ] PostgreSQL database configured (`DEBUG=False` rejects other engines)
- [ ] Huey consumer and scheduled polling trigger
- [ ] systemd service for Daphne
- [ ] Nginx/Apache reverse proxy
- [ ] SSL certificates
- [ ] Log rotation
- [ ] Monitoring alerts
- [ ] Backup strategy

For full documentation, see README.md
