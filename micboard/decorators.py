"""
Rate limiting decorators for micboard views.
"""

import logging
import time
from functools import wraps

from django.core.cache import cache
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def rate_limit_view(max_requests: int = 60, window_seconds: int = 60, key_func=None):
    """
    Rate limit decorator for Django views using sliding window algorithm.

    Args:
        max_requests: Maximum number of requests allowed in the time window
        window_seconds: Time window in seconds
        key_func: Optional function to generate cache key from request (default: uses IP)

    Example:
        @rate_limit_view(max_requests=10, window_seconds=60)
        def my_view(request):
            return JsonResponse({'data': 'value'})
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Generate cache key
            if key_func:
                cache_key = key_func(request)
            else:
                # Default: use IP address
                ip = get_client_ip(request)
                cache_key = f"rate_limit_{view_func.__name__}_{ip}"

            # Get current request timestamps
            now = time.time()
            window_key = f"{cache_key}_window"
            request_times = cache.get(window_key, [])

            # Remove timestamps outside the current window
            request_times = [t for t in request_times if now - t < window_seconds]

            # Check if rate limit exceeded
            if len(request_times) >= max_requests:
                oldest_request = min(request_times)
                retry_after = int(window_seconds - (now - oldest_request)) + 1

                logger.warning(
                    "Rate limit exceeded for %s: %d/%d requests in %ds window",
                    cache_key,
                    len(request_times),
                    max_requests,
                    window_seconds,
                )

                return JsonResponse(
                    {
                        "error": "Rate limit exceeded",
                        "detail": f"Maximum {max_requests} requests per {window_seconds} seconds",
                        "retry_after": retry_after,
                    },
                    status=429,
                    headers={"Retry-After": str(retry_after)},
                )

            # Add current request timestamp
            request_times.append(now)
            cache.set(window_key, request_times, timeout=window_seconds + 1)

            # Call the view
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def get_client_ip(request):
    """
    Extract client IP address from request, considering proxies.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR", "unknown")
    return ip


def rate_limit_user(max_requests: int = 100, window_seconds: int = 60):
    """
    Rate limit decorator for authenticated users.
    Uses user ID instead of IP address for the cache key.

    Example:
        @login_required
        @rate_limit_user(max_requests=30, window_seconds=60)
        def my_view(request):
            return JsonResponse({'data': 'value'})
    """

    def key_func(request):
        if request.user.is_authenticated:
            return f"rate_limit_user_{request.user.id}"
        else:
            ip = get_client_ip(request)
            return f"rate_limit_anon_{ip}"

    return rate_limit_view(max_requests, window_seconds, key_func)
