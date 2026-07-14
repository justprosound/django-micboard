from __future__ import annotations

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from django.core.cache import cache

logger = logging.getLogger(__name__)
_CallableT = TypeVar("_CallableT", bound=Callable[..., Any])


def rate_limit(*, calls_per_second: float = 10.0) -> Callable[[_CallableT], _CallableT]:
    """Rate-limit calls to a decorated client method through the shared cache."""

    def _decorator(func: _CallableT) -> _CallableT:
        @wraps(func)
        def _wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
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

        return cast(_CallableT, _wrapper)

    return _decorator
