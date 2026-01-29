"""Caching utilities for django-micboard.

Provides decorators and utilities for caching service results.
"""

from __future__ import annotations

import hashlib
import json
import logging
from functools import wraps
from typing import Any, Callable

from django.core.cache import cache

logger = logging.getLogger(__name__)


def cache_key(*args, **kwargs) -> str:
    """Generate cache key from arguments.

    Args:
        *args: Positional arguments to include in key.
        **kwargs: Keyword arguments to include in key.

    Returns:
        Cache key string.
    """
    # Create hashable representation
    key_data = {"args": args, "kwargs": sorted(kwargs.items())}
    key_str = json.dumps(key_data, sort_keys=True, default=str)
    key_hash = hashlib.md5(key_str.encode(), usedforsecurity=False).hexdigest()
    return f"micboard:{key_hash}"


def cache_service_result(*, timeout: int = 300):
    """Decorator to cache service method results.

    Args:
        timeout: Cache timeout in seconds. Defaults to 300 (5 minutes).

    Returns:
        Decorated function.

    Example:
        @cache_service_result(timeout=60)
        @staticmethod
        def get_active_receivers() -> QuerySet:
            return WirelessChassis.objects.filter(is_online=True)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Generate cache key
            key = f"{func.__module__}.{func.__qualname__}:{cache_key(*args, **kwargs)}"

            # Try to get from cache
            result = cache.get(key)
            if result is not None:
                return result

            # Call function and cache result
            result = func(*args, **kwargs)
            cache.set(key, result, timeout)
            return result

        return wrapper

    return decorator


def invalidate_cache(pattern: str) -> int:
    """Invalidate cache entries matching pattern.

    Args:
        pattern: Cache key pattern to match.

    Returns:
        Number of keys invalidated.

    Example:
        invalidate_cache("micboard:HardwareService.*")
    """
    # Note: This requires Django cache backend that supports pattern matching
    # (e.g., Redis). For simple cache backends, this is a no-op.
    try:
        if hasattr(cache, "delete_pattern"):
            return cache.delete_pattern(pattern)
    except Exception:
        logger.exception("Error invalidating cache pattern: %s", pattern)
    return 0


class CachedProperty:
    """Descriptor for cached instance properties.

    Example:
        class MyModel(models.Model):
            @CachedProperty
            def expensive_calculation(self) -> int:
                return sum(range(1000000))
    """

    def __init__(self, func: Callable):
        """Initialize the cached property descriptor for a callable."""
        self.func = func
        self.name = func.__name__

    def __get__(self, instance: Any, owner: type | None = None) -> Any:
        if instance is None:
            return self

        # Check if already cached on instance
        cache_attr = f"_cached_{self.name}"
        if not hasattr(instance, cache_attr):
            # Calculate and cache
            result = self.func(instance)
            setattr(instance, cache_attr, result)

        return getattr(instance, cache_attr)


def cache_queryset(*, timeout: int = 300):
    """Cache QuerySet results.

    Args:
        timeout: Cache timeout in seconds. Defaults to 300.

    Returns:
        Decorated function that caches QuerySet results.

    Example:
        @cache_queryset(timeout=60)
        def get_active_devices() -> QuerySet:
            return WirelessChassis.objects.filter(is_online=True)
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            key = f"qs:{func.__module__}.{func.__qualname__}:{cache_key(*args, **kwargs)}"

            # Try to get from cache
            cached_pks = cache.get(key)
            if cached_pks is not None:
                # Return QuerySet filtered by cached PKs
                qs = func(*args, **kwargs)
                return qs.filter(pk__in=cached_pks)

            # Get QuerySet and cache PKs
            qs = func(*args, **kwargs)
            pks = list(qs.values_list("pk", flat=True))
            cache.set(key, pks, timeout)

            return qs

        return wrapper

    return decorator


# Preset cache configurations
CACHE_SHORT = 60  # 1 minute
CACHE_MEDIUM = 300  # 5 minutes
CACHE_LONG = 900  # 15 minutes
CACHE_HOUR = 3600  # 1 hour
