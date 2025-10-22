# Quick Start Guide

> **⚠️ ACTIVE DEVELOPMENT**: This project has not been released. This guide is for development and testing only.

## Prerequisites

1. Python 3.9+ installed
2. Shure System API server installed and running
3. Network access to Shure devices

## Installation Steps

### 1. Clone and Install

```bash
git clone https://github.com/justprosound/django-micboard.git
cd django-micboard
pip install -e .
```

### 2. Add to Django Project

Add to `settings.py`:
```python
INSTALLED_APPS = [
    # ... existing apps
    'channels',
    'micboard',
]

# Micboard configuration
MICBOARD_CONFIG = {
    'SHURE_API_BASE_URL': 'http://localhost:10000',  # or https:// for SSL
    'SHURE_API_SHARED_KEY': 'your-shared-secret-here',  # Required: from Shure System API
    'SHURE_API_VERIFY_SSL': True,  # Set to False only for self-signed certificates
}

# Channels configuration
ASGI_APPLICATION = 'your_project.asgi.application'
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer'
    },
}
```

### 3. Update ASGI Configuration

Update `asgi.py`:
```python
import os
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
