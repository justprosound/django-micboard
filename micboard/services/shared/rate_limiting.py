"""Rate limiting service logic for micboard."""

import logging
import time

from django.core.cache import cache

logger = logging.getLogger(__name__)


def check_rate_limit(cache_key, max_requests, window_seconds):
    """Check and update rate limit for a given cache key."""
    now = time.time()
    window_key = f"{cache_key}_window"
    try:
        request_times = cache.get(window_key, [])
    except Exception:
        logger.debug("Cache read failed, allowing request: %s", cache_key)
        request_times = []

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
        return False, retry_after, request_times

    # Add current request timestamp
    request_times.append(now)
    try:
        cache.set(window_key, request_times, timeout=window_seconds + 1)
    except Exception:
        logger.debug("Cache write failed, but allowing request: %s", cache_key)
    return True, None, request_times


def get_client_ip(request):
    """Extract client IP address from request, considering proxies."""
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR", "unknown")
    return ip


def get_user_cache_key(request, view_func_name):
    if hasattr(request, "user") and getattr(request.user, "is_authenticated", False):
        return f"rate_limit_user_{request.user.id}"
    else:
        ip = get_client_ip(request)
        return f"rate_limit_anon_{view_func_name}_{ip}"
