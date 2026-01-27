"""Centralized dependency checking for optional features."""

import importlib.util

def is_installed(package_name: str) -> bool:
    """Check if a Python package is installed."""
    return importlib.util.find_spec(package_name) is not None

# Core optional features
HAS_CHANNELS = is_installed("channels")
HAS_DJANGO_Q = is_installed("django_q")
HAS_DJANGO_FILTER = is_installed("django_filters")
HAS_IMPORT_EXPORT = is_installed("import_export")
HAS_ADMIN_SORTABLE = is_installed("adminsortable2")
HAS_SIMPLE_HISTORY = is_installed("simple_history")
HAS_RANGE_FILTER = is_installed("rangefilter")
HAS_UNFOLD = is_installed("unfold")
HAS_HEALTH_CHECK = is_installed("health_check")
HAS_CRYPTOGRAPHY = is_installed("django_cryptography")
