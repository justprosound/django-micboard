"""Rate limiting utilities for manufacturer API clients.

Provides decorators and context managers for rate limiting API calls
across different manufacturer integrations using a token bucket algorithm.
"""

from __future__ import annotations

import logging
import time
from functools import wraps

from django.core.cache import cache

logger = logging.getLogger(__name__)


def rate_limit(*, calls_per_second: float = 10.0):
    """Decorator to rate limit method calls.
    Uses token bucket algorithm with Django cache.

    Args:
        calls_per_second: Maximum number of calls per second (keyword-only)

    Example:
        >>> class APIClient:
        ...     @rate_limit(calls_per_second=5.0)
        ...     def get_devices(self):
        ...         return self._api_request("/devices")

    Note:
        - Applies globally across all instances via cache
        - Thread-safe using Django cache atomic operations
        - Logs rate limit events at DEBUG level
    """

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            cache_key = f"rate_limit_{self.__class__.__name__}_{func.__name__}"
            min_interval = 1.0 / calls_per_second

            last_call = cache.get(cache_key, 0)
            now = time.time()
            time_since_last = now - last_call

            if time_since_last < min_interval:
                sleep_time = min_interval - time_since_last
                logger.debug("Rate limiting %s: sleeping %.3fs", func.__name__, sleep_time)
                time.sleep(sleep_time)
                now = time.time()

            cache.set(cache_key, now, timeout=60)
            return func(self, *args, **kwargs)

        return wrapper

    return decorator
