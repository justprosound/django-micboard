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

`django-micboard` is configured through a single dictionary in your `settings.py` called `MICBOARD_CONFIG`. The following keys are available:

| Key | Description | Default |
| --- | --- | --- |
| `SHURE_API_BASE_URL` | The base URL of the Shure System API. | `"http://localhost:8080"` |
| `SHURE_API_USERNAME` | The username for the Shure System API (optional). | `None` |
| `SHURE_API_PASSWORD` | The password for the Shure System API (optional). | `None` |
| `SHURE_API_TIMEOUT` | The timeout in seconds for API requests. | `10` |
| `SHURE_API_VERIFY_SSL` | Whether to verify SSL certificates for the API. | `True` |
| `SHURE_API_MAX_RETRIES` | The maximum number of retries for failed API requests. | `3` |
| `SHURE_API_RETRY_BACKOFF` | The backoff factor for retries (in seconds). | `0.5` |
| `SHURE_API_RETRY_STATUS_CODES` | A list of HTTP status codes to retry on. | `[429, 500, 502, 503, 504]` |
| `POLL_INTERVAL` | The interval in seconds between device polls. | `5` |
| `CACHE_TIMEOUT` | The timeout in seconds for caching API responses. | `30` |
| `TRANSMITTER_INACTIVITY_SECONDS` | Inactivity threshold (seconds) before a transmitter session is considered ended and a new session started on next sample. Used to detect short outages. | `10` |

Example:

```python
MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": "http://my-shure-api.local:8080",
    "POLL_INTERVAL": 10,
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

## Health Checks

You can check the health of the Shure System API connection using the management command:

```bash
python manage.py check_api_health
```

For JSON output:

```bash
python manage.py check_api_health --json
```

The health check will show:
- API connectivity status
- Response status codes
- Consecutive failure count
- Last successful request timestamp
