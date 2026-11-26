---
title: "Quick Start Guide"
type: tutorial
audience: developer
---
Get django-micboard up and running with your Shure wireless microphone system in minutes.

## Prerequisites

- Python 3.14+
- Django 5.2 through 6.0
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
uv run --no-sync python manage.py discovery_add_devices --ips 192.0.2.100,192.0.2.101

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

## Check the installation

1. Run Django's checks:

   ```bash
   uv run --no-sync python manage.py check
   ```

2. Sign in to the Django admin and open the Micboard models.
3. Check connection status:

   ```bash
   uv run --no-sync python manage.py realtime_status --verbose
   ```

## Next steps

- [Manage assignments and devices in the admin](guides/admin-interface.md)
- [Monitor devices](guides/monitoring.md)
- [Set up real-time updates](guides/realtime-updates.md)
- [HTTP endpoints](api/endpoints.md)
- [Shure troubleshooting](guides/shure-troubleshooting.md) if the API connection or discovery does not work
