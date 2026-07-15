"""Rate limiting service logic for micboard."""

from __future__ import annotations

import logging
import time

from django.core.cache import cache
from django.http import HttpRequest

logger = logging.getLogger(__name__)


def check_rate_limit(
    cache_key: str,
    max_requests: int,
    window_seconds: int,
) -> tuple[bool, int | None, list[float]]:
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


def get_client_ip(request: HttpRequest) -> str:
    """Extract client IP address from request, considering proxies."""
    x_forwarded_for = request.headers.get("x-forwarded-for")
    ip = (
        x_forwarded_for.split(",")[0].strip()
        if x_forwarded_for
        else request.META.get("REMOTE_ADDR", "unknown")
    )
    return ip


def get_user_cache_key(request: HttpRequest, view_func_name: str) -> str:
    """Return a stable authenticated-user or anonymous-client cache key."""
    if hasattr(request, "user") and getattr(request.user, "is_authenticated", False):
        return f"rate_limit_user_{request.user.id}"
    ip = get_client_ip(request)
    return f"rate_limit_anon_{view_func_name}_{ip}"
