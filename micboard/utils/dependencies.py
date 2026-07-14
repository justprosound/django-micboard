"""Centralized dependency checking for optional features."""

import importlib.util
from collections.abc import Callable
from functools import cache
from typing import Any

from django.apps import AppConfig, apps
from django.conf import settings
from django.utils.module_loading import import_string


def is_installed(package_name: str) -> bool:
    """Check if a Python package is installed."""
    return importlib.util.find_spec(package_name) is not None


def is_django_app_configured(package_name: str, app_name: str | None = None) -> bool:
    """Return whether an optional Django package is installed and enabled.

    Importability alone is insufficient for Django integrations. Their models,
    templates, and app hooks are only available when the host project includes
    the application in ``INSTALLED_APPS``.
    """
    if not is_installed(package_name) or not settings.configured:
        return False

    configured_name = app_name or package_name
    if apps.apps_ready:
        return apps.is_installed(configured_name)

    for entry in settings.INSTALLED_APPS:
        if entry == configured_name:
            return True
        try:
            app_config = import_string(entry)
        except ImportError:
            continue
        if (
            isinstance(app_config, type)
            and issubclass(app_config, AppConfig)
            and app_config.name == configured_name
        ):
            return True
    return False


# Core optional features
HAS_CHANNELS = is_installed("channels")
HAS_DJANGO_FILTER = is_installed("django_filters")
HAS_IMPORT_EXPORT = is_django_app_configured("import_export")
HAS_ADMIN_SORTABLE = is_django_app_configured("adminsortable2")
HAS_SIMPLE_HISTORY = is_django_app_configured("simple_history")
HAS_RANGE_FILTER = is_django_app_configured("rangefilter")
HAS_UNFOLD = is_django_app_configured("unfold")
HAS_UNFOLD_FILTERS = HAS_UNFOLD and is_django_app_configured("unfold.contrib.filters")
HAS_UNFOLD_IMPORT_EXPORT = (
    HAS_UNFOLD and HAS_IMPORT_EXPORT and is_django_app_configured("unfold.contrib.import_export")
)
HAS_CRYPTOGRAPHY = is_installed("django_cryptography")


def huey_is_configured() -> bool:
    """Return whether the host configured Huey's native Django integration."""
    if not is_installed("huey"):
        return False

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
