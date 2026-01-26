# Micboard Configuration

To use `django-micboard` in your project, you need to configure your project's `settings.py` file.

## INSTALLED_APPS

Add `micboard` and `channels` to your `INSTALLED_APPS` setting:

```python
INSTALLED_APPS = [
    # ... other apps
    "channels",
    "micboard",
]
```

## MICBOARD_CONFIG

`django-micboard` is configured through a single dictionary in your `settings.py` called `MICBOARD_CONFIG`. All keys are optional except where noted. The following keys are available:

| Key | Description | Default |
|-----|-------------|---------|
| `SHURE_API_BASE_URL` | The base URL of the Shure System API (required) | `"http://localhost:8080"` |
| `SHURE_API_SHARED_KEY` | The shared secret API key for Shure System API | `None` |
| `SHURE_API_TIMEOUT` | Timeout in seconds for API requests | `10` |
| `SHURE_API_VERIFY_SSL` | Whether to verify SSL certificates | `True` |
| `SHURE_API_MAX_RETRIES` | Maximum number of retries for failed requests | `3` |
| `SHURE_API_RETRY_BACKOFF` | Backoff factor for retries (seconds) | `0.5` |
| `SHURE_API_RETRY_STATUS_CODES` | HTTP status codes to retry | `[429, 500, 502, 503, 504]` |
| `POLL_INTERVAL` | Interval in seconds between device polls | `5` |
| `CACHE_TIMEOUT` | Timeout in seconds for API response caching | `30` |
| `TRANSMITTER_INACTIVITY_SECONDS` | Seconds before transmitter marked inactive | (varies) |

## Authentication

The Shure System API requires authentication using a shared secret API key. This key is automatically generated when the Shure System API runs for the first time.

### API Key Authentication (Shared Secret)

Configure the shared secret in your settings:

```python
MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": "http://my-shure-api.local:10000",
    "SHURE_API_SHARED_KEY": "your-shared-secret-here",
}
```

The shared secret is automatically generated when the Shure System API runs for the first time. On Windows systems, it can be found at:
```
C:\ProgramData\Shure\SystemAPI\Standalone\Security\sharedkey.txt
```

**Note**: The shared secret is required for all API requests to the Shure System API.

## SSL/TLS Configuration

The Shure System API supports both HTTP and HTTPS connections. When using HTTPS, SSL certificate verification is enabled by default for security.

### Self-Signed Certificates

⚠️ **Security Warning**: If your Shure System API uses self-signed certificates, you must disable SSL verification. This reduces security but is necessary for self-signed certificates.

To disable SSL verification:

```python
MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": "https://my-shure-api.local:10000",
    "SHURE_API_VERIFY_SSL": False,  # ⚠️ Only use with self-signed certificates
}
```

### Production Recommendations

For production deployments:
- Use valid SSL certificates from a trusted Certificate Authority
- Keep `SHURE_API_VERIFY_SSL: True` (default)
- Consider using mutual TLS authentication if supported by your Shure System API

Example with HTTPS:

```python
MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": "https://my-shure-api.local:10000",
    "SHURE_API_VERIFY_SSL": True,  # Recommended for production
    "SHURE_API_TIMEOUT": 15,
    "POLL_INTERVAL": 10,
}
```

## Polling Configuration

Configure device polling frequency and behavior:

```python
MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": "http://my-shure-api.local:10000",
    "POLL_INTERVAL": 10,  # Poll every 10 seconds
    "CACHE_TIMEOUT": 60,  # Cache responses for 60 seconds
    "TRANSMITTER_INACTIVITY_SECONDS": 30,  # Mark transmitters inactive after 30s
}
```

## WebSocket Support (Channels)

For real-time updates, `django-micboard` uses Django Channels. You need to configure an ASGI application and a channel layer.

In your project's `settings.py`:

```python
ASGI_APPLICATION = "your_project.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
        # For production, it is highly recommended to use Redis:
        # "BACKEND": "channels_redis.core.RedisChannelLayer",
        # "CONFIG": {
        #     "hosts": [("127.0.0.1", 6379)],
        # },
    },
}
```

Make sure your project has an `asgi.py` file.

## Caching

The app uses Django's cache framework to cache API responses. You should configure a cache backend in your `settings.py`. For development, the local memory cache is sufficient.

```python
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "micboard-cache",
    }
}
```

For production, consider using a more robust cache backend like Redis or Memcached.

## Logging

The app uses the `micboard` logger. You can configure it in your `LOGGING` setting:

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "micboard": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}
```

## Management Commands

The app provides several management commands for device management and monitoring:

```bash
# Poll devices from manufacturers
python manage.py poll_devices

# Sync discovery results
python manage.py sync_discovery

# Add Shure devices manually
python manage.py add_shure_devices

# Subscribe to real-time status
python manage.py realtime_status

# WebSocket subscriptions
python manage.py websocket_subscribe

# Server-Sent Events subscription
python manage.py sse_subscribe
```

See [API Reference](api/management.md) for detailed command documentation.
