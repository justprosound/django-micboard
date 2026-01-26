# Django Micboard Configuration Guide

This guide covers all configuration options for django-micboard, including development setup, Shure System API integration, and production deployment.

## Quick Start

1. **Create environment file**:
   ```bash
   cp .env.local.example .env.local
   ```

2. **Edit with your values**:
   ```bash
   # .env.local
   DJANGO_SECRET_KEY=your-secret-key
   MICBOARD_SHURE_API_BASE_URL=https://localhost:10000
   MICBOARD_SHURE_API_SHARED_KEY=<from-shure-config>
   MICBOARD_SHURE_API_VERIFY_SSL=false
   ```

3. **Load and run**:
   ```bash
   source .env.local
   python manage.py migrate
   python manage.py runserver
   ```

## INSTALLED_APPS

Add `micboard` and `channels` to your Django settings:

```python
INSTALLED_APPS = [
    # Django
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'django_filters',
    'corsheaders',
    'channels',

    # Micboard
    'micboard',
]
```

## MICBOARD_CONFIG Dictionary

Configure django-micboard through a `MICBOARD_CONFIG` dictionary in `settings.py`:

```python
MICBOARD_CONFIG = {
    # Shure System API Configuration
    "SHURE_API_BASE_URL": os.environ.get(
        "MICBOARD_SHURE_API_BASE_URL",
        "https://localhost:10000"
    ),
    "SHURE_API_SHARED_KEY": os.environ.get("MICBOARD_SHURE_API_SHARED_KEY"),
    "SHURE_API_VERIFY_SSL": os.environ.get(
        "MICBOARD_SHURE_API_VERIFY_SSL",
        "false"
    ).lower() in ('true', '1', 'yes'),
    "SHURE_API_TIMEOUT": int(os.environ.get("MICBOARD_SHURE_API_TIMEOUT", "10")),

    # Rate Limiting
    "RATE_LIMIT_ENABLED": True,
    "RATE_LIMIT_DEFAULT": "100/hour",

    # Device Polling
    "POLLING_INTERVAL_SECONDS": 30,  # How often to poll devices
    "POLLING_TIMEOUT_SECONDS": 10,   # Poll operation timeout

    # WebSocket
    "WEBSOCKET_HEARTBEAT_INTERVAL": 30,
    "WEBSOCKET_MAX_CONNECTIONS": 100,
}
```

## Shure System API Configuration

### Required Settings

```python
MICBOARD_CONFIG = {
    # The Shure System API base URL (typically https://localhost:10000)
    "SHURE_API_BASE_URL": "https://localhost:10000",

    # Shared key from Shure API config for authentication
    # Get from: C:\ProgramData\Shure\SystemAPI\Standalone\Security\sharedkey.txt
    "SHURE_API_SHARED_KEY": "your-shared-key",

    # Verify SSL certificates (set false for self-signed)
    "SHURE_API_VERIFY_SSL": False,

    # Request timeout in seconds
    "SHURE_API_TIMEOUT": 10,
}
```

### Optional Settings

```python
MICBOARD_CONFIG = {
    # Retry configuration
    "SHURE_API_MAX_RETRIES": 3,
    "SHURE_API_RETRY_BACKOFF": 0.5,  # seconds
    "SHURE_API_RETRY_STATUS_CODES": [429, 500, 502, 503, 504],

    # Rate limiting
    "SHURE_API_RATE_LIMIT_ENABLED": True,
    "SHURE_API_RATE_LIMIT_REQUESTS": 120,
    "SHURE_API_RATE_LIMIT_WINDOW": 60,  # seconds

    # WebSocket URL (auto-generated if not provided)
    # "SHURE_API_WEBSOCKET_URL": "wss://localhost:10000/api/v1/devices/ws",
}
```

### Important: GUID Configuration

The **NetworkInterfaceId GUID** in the Shure System API config is critical for device discovery.

```json
{
  "Discovery": {
    "NetworkInterfaceId": "{A283C67D-499A-4B7E-B628-F74E8061FCE2}"
  }
}
```

**If this GUID is wrong:**
- ✗ 0 devices will be discovered (silently fails)
- ✗ No error messages in logs
- ✗ Service appears healthy
- ✓ Firewall logs show outbound packets (but to wrong interface)

**See**: [SHURE_NETWORK_GUID_TROUBLESHOOTING.md](SHURE_NETWORK_GUID_TROUBLESHOOTING.md) for diagnosis and fix.

## Django Channels Configuration

WebSocket support requires Django Channels:

```python
# settings.py

# Use Daphne as ASGI server
INSTALLED_APPS = [
    'daphne',
    # ... other apps
]

# Channel Layers (Redis)
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [("127.0.0.1", 6379)],
        },
    },
}

# ASGI Application
ASGI_APPLICATION = "demo.asgi.application"
```

## REST Framework Configuration

```python
REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
}
```

## Rate Limiting

Micboard includes built-in rate limiting via decorators:

```python
from micboard.decorators import rate_limit_view

# Limit to 100 requests per hour
@rate_limit_view(max_requests=100, window_seconds=3600)
def my_view(request):
    return Response(...)

# Limit to 10 requests per minute
@rate_limit_view(max_requests=10, window_seconds=60)
def expensive_operation(request):
    return Response(...)
```

## Device Polling Configuration

```python
MICBOARD_CONFIG = {
    # How often to poll devices for updates (seconds)
    "POLLING_INTERVAL_SECONDS": 30,

    # How long each poll can take before timeout (seconds)
    "POLLING_TIMEOUT_SECONDS": 10,

    # What to do if poll fails
    "POLLING_ERROR_HANDLER": "micboard.tasks.handle_polling_error",
}
```

Run polling with:
```bash
python manage.py poll_devices
```

## Environment Variables Reference

| Variable | Type | Default | Required |
|----------|------|---------|----------|
| `MICBOARD_SHURE_API_BASE_URL` | str | `https://localhost:10000` | Yes |
| `MICBOARD_SHURE_API_SHARED_KEY` | str | - | Yes |
| `MICBOARD_SHURE_API_VERIFY_SSL` | bool | `false` | No |
| `MICBOARD_SHURE_API_TIMEOUT` | int | `10` | No |
| `DJANGO_SECRET_KEY` | str | - | Yes* |
| `DEBUG` | bool | `False` | No |

*Required for production

## Development Setup

```python
# settings.py (development)

DEBUG = True
ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'example.local']

# Use SQLite for development
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# File-based cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}
```

## Production Setup

```python
# settings.py (production)

DEBUG = False
ALLOWED_HOSTS = ['yourdomain.com', 'www.yourdomain.com']

# Use PostgreSQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'micboard',
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST'),
        'PORT': '5432',
    }
}

# Redis cache
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}

# Security headers
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
HSTS_SECONDS = 31536000
```

## Logging Configuration

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'micboard.log',
        },
    },
    'loggers': {
        'micboard': {
            'handlers': ['console', 'file'],
            'level': os.environ.get('LOG_LEVEL', 'INFO'),
        },
    },
}
```

## Troubleshooting Configuration

### "SHURE_API_SHARED_KEY is required"

**Problem**: Script fails with authentication error.

**Solution**:
1. Check environment variable is set:
   ```bash
   echo $MICBOARD_SHURE_API_SHARED_KEY
   ```

2. Or add to `settings.py`:
   ```python
   MICBOARD_CONFIG["SHURE_API_SHARED_KEY"] = "your-key"
   ```

### "Connection refused" to API

**Problem**: Can't connect to Shure System API.

**Solution**:
1. Check API is running:
   ```powershell
   Get-Service -Name "*Shure*"
   ```

2. Check URL is correct:
   ```bash
   curl -k https://localhost:10000/api/v1/devices
   ```

### "0 devices discovered"

**Problem**: Devices are configured but not being discovered.

**Solution**: See [SHURE_NETWORK_GUID_TROUBLESHOOTING.md](SHURE_NETWORK_GUID_TROUBLESHOOTING.md)

This is almost always caused by incorrect NetworkInterfaceId GUID.

## Next Steps

1. [Quick Start Guide](quickstart.md) - Get running quickly
2. [Development Setup](../development/setup.md) - Local development environment
3. [Testing Guide](../development/testing.md) - Run tests
4. [API Reference](../api/endpoints.md) - Explore endpoints
5. [Architecture](architecture.md) - Understand system design

---

**Last Updated**: January 21, 2026
**Status**: Production Ready
