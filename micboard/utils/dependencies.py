"""Centralized dependency checking for optional features."""

import importlib.util
from collections.abc import Callable
from functools import cache
from typing import Any


def is_installed(package_name: str) -> bool:
    """Check if a Python package is installed."""
    return importlib.util.find_spec(package_name) is not None


# Core optional features
HAS_CHANNELS = is_installed("channels")
HAS_DJANGO_FILTER = is_installed("django_filters")
HAS_IMPORT_EXPORT = is_installed("import_export")
HAS_ADMIN_SORTABLE = is_installed("adminsortable2")
HAS_SIMPLE_HISTORY = is_installed("simple_history")
HAS_RANGE_FILTER = is_installed("rangefilter")
HAS_UNFOLD = is_installed("unfold")
HAS_CRYPTOGRAPHY = is_installed("django_cryptography")


def huey_is_configured() -> bool:
    """Return whether the host configured Huey's native Django integration."""
    if not is_installed("huey"):
        return False

    from django.apps import apps
    from django.conf import settings

    if not settings.configured:
        return False
    return apps.is_installed("huey.contrib.djhuey") and getattr(settings, "HUEY", None) is not None


@cache
def register_huey_task(func: Callable[..., Any]) -> Any:
    """Register a database task that is enqueued after transaction commit."""
    if not huey_is_configured():
        raise RuntimeError(
            "Native Huey is not configured; add huey.contrib.djhuey and settings.HUEY"
        )

    from huey.contrib.djhuey import on_commit_task

    return on_commit_task()(func)


def enqueue_huey_task(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Enqueue a registered callable on the native Huey queue."""
    return register_huey_task(func)(*args, **kwargs)
