"""
Configuration helper for Micboard Django App with Shure System API

Add this to your Django project's settings.py file:
"""

# Micboard Configuration
MICBOARD_CONFIG = {
    # Shure System API connection settings
    'SHURE_API_BASE_URL': 'http://localhost:8080',
    'SHURE_API_USERNAME': None,  # Optional
    'SHURE_API_PASSWORD': None,  # Optional
    'SHURE_API_TIMEOUT': 10,  # seconds
    'SHURE_API_VERIFY_SSL': True,
    
    # Retry configuration for API client
    'SHURE_API_MAX_RETRIES': 3,
    'SHURE_API_RETRY_BACKOFF': 0.5,  # seconds between retries (exponential)
    'SHURE_API_RETRY_STATUS_CODES': [429, 500, 502, 503, 504],  # HTTP codes to retry
    
    # Device polling settings
    'POLL_INTERVAL': 5,  # seconds between polls
    'CACHE_TIMEOUT': 30,  # seconds to cache API responses
}

# Add to INSTALLED_APPS
INSTALLED_APPS = [
    # ... other apps
    'channels',
    'micboard',
]

# Channels configuration for WebSocket support
ASGI_APPLICATION = 'your_project.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer'
        # For production, use Redis:
        # 'BACKEND': 'channels_redis.core.RedisChannelLayer',
        # 'CONFIG': {
        #     "hosts": [('127.0.0.1', 6379)],
        # },
    },
}

# Cache configuration (for device data caching)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'micboard-cache',
        # For production, consider Redis or Memcached
    }
}

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': 'micboard.log',
        },
    },
    'loggers': {
        'micboard': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
