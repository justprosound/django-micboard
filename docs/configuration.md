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

| `SHURE_API_BASE_URL` | The base URL of the Shure System API. | `"http://localhost:10000"` |
| `SHURE_API_SHARED_KEY` | The shared secret API key for the Shure System API (required). | `None` |
| `SHURE_API_TIMEOUT` | The timeout in seconds for API requests. | `10` |
| `SHURE_API_VERIFY_SSL` | Whether to verify SSL certificates for the API. | `True` |
| `SHURE_API_MAX_RETRIES` | The maximum number of retries for failed API requests. | `3` |
| `SHURE_API_RETRY_BACKOFF` | The backoff factor for retries (in seconds). | `0.5` |
| `SHURE_API_RETRY_STATUS_CODES` | A list of HTTP status codes to retry on. | `[429, 500, 502, 503, 504]` |

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
}
```
| `POLL_INTERVAL` | The interval in seconds between device polls. | `5` |
| `CACHE_TIMEOUT` | The timeout in seconds for caching API responses. | `30` |
| `EMAIL_RECIPIENTS` | A list of email addresses to send alerts to. | `[]` |
| `EMAIL_FROM` | The email address to send alerts from. | `"micboard@localhost"` |

Example:

```python
MICBOARD_CONFIG = {
    "SHURE_API_BASE_URL": "http://my-shure-api.local:10000",
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

## Email Configuration

`django-micboard` uses Django's built-in email system for sending alert notifications. Configure your email settings in `settings.py`:

```python
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = "your-email@gmail.com"
EMAIL_HOST_PASSWORD = "your-app-password"
DEFAULT_FROM_EMAIL = "micboard@yourdomain.com"
```

For alert notifications, configure recipients in `MICBOARD_CONFIG`:

```python
MICBOARD_CONFIG = {
    # ... other settings
    "EMAIL_RECIPIENTS": ["admin@yourdomain.com", "tech@yourdomain.com"],
    "EMAIL_FROM": "micboard@yourdomain.com",
}
```

Individual users can also configure their own alert preferences through the admin interface, including:
- Email notification method (email, WebSocket, or both)
- Custom email address for alerts
- Battery and signal thresholds
- Quiet hours for notifications

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
