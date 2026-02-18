from functools import wraps

from django.http import JsonResponse

from micboard.services.shared import rate_limiting


def rate_limit_view(max_requests: int = 60, window_seconds: int = 60, key_func=None):
    """Rate limit decorator for Django views using sliding window algorithm (delegates to service)."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if key_func:
                cache_key = key_func(request)
            else:
                ip = rate_limiting.get_client_ip(request)
                cache_key = f"rate_limit_{view_func.__name__}_{ip}"

            allowed, retry_after, _ = rate_limiting.check_rate_limit(
                cache_key, max_requests, window_seconds
            )
            if not allowed:
                return JsonResponse(
                    {
                        "error": "Rate limit exceeded",
                        "detail": f"Maximum {max_requests} requests per {window_seconds} seconds",
                        "retry_after": retry_after,
                    },
                    status=429,
                    headers={"Retry-After": str(retry_after)},
                )
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


# Alias for external usage (no local body required)
get_client_ip = rate_limiting.get_client_ip


def rate_limit_user(max_requests: int = 100, window_seconds: int = 60):
    """Rate limit decorator for authenticated users (delegates to service for cache key)."""

    def key_func(request):
        return rate_limiting.get_user_cache_key(request, view_func_name="user_view")

    return rate_limit_view(max_requests, window_seconds, key_func)
