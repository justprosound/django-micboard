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
    'SHURE_API_BASE_URL': 'http://localhost:8080',
    'SHURE_API_USERNAME': None,
    'SHURE_API_PASSWORD': None,
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
from micboard.routing import websocket_urlpatterns

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

### 7. Access the Dashboard
Open browser to: `http://localhost:8000/micboard/`

## Testing the Installation

1. Check API connection:
```bash
curl http://localhost:8080/api/v1/devices
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
- Check Shure System API is running: `curl http://localhost:8080/api/v1/devices`
- Verify devices are powered on and connected
- Check network connectivity

**Problem**: WebSocket not connecting
- Ensure Daphne is running (not standard Django server)
- Check browser console for errors
- Verify WebSocket URL: `ws://localhost:8000/micboard/ws`

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
