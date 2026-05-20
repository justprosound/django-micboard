"""Common integration utilities shared across all manufacturer implementations.

This module provides shared base classes and utilities for:
- Rate limiting (decorators and context managers)
- Exception handling (base exception hierarchy)
- HTTP client helpers
- Data transformation utilities
- IP validation and hostname validation
- Plugin discovery (get_manufacturer_plugin)
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from .base import BaseAPIClient, BasePlugin, ManufacturerPlugin
from .exceptions import APIError, APIRateLimitError
from .rate_limiter import rate_limit
from .utils import validate_hostname, validate_ipv4_address, validate_ipv4_list

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "APIError",
    "APIRateLimitError",
    "BaseAPIClient",
    "BasePlugin",
    "ManufacturerPlugin",
    "get_manufacturer_plugin",
    "rate_limit",
    "validate_hostname",
    "validate_ipv4_address",
    "validate_ipv4_list",
]


def get_manufacturer_plugin(code: str) -> type[ManufacturerPlugin]:
    """Return the plugin class for a manufacturer code.

    This function attempts to import ``micboard.integrations.<code>.plugin`` and
    locate the plugin class. It prefers a class named <CodeTitle>Plugin, then
    falls back to the first exported class whose name ends with 'Plugin' or
    which implements a ``get_devices`` method.
    """
    code = str(code)
    module_paths = [f"micboard.integrations.{code}.plugin", f"micboard.integrations.{code}"]
    mod = None
    for path in module_paths:
        try:
            mod = importlib.import_module(path)
            break
        except ModuleNotFoundError:
            continue

    if mod is None:
        raise ModuleNotFoundError(f"No integration module found for manufacturer '{code}'")

    candidate_name = "".join(part.capitalize() for part in code.split("_")) + "Plugin"
    if hasattr(mod, candidate_name):
        cls = getattr(mod, candidate_name)
        if isinstance(cls, type):
            return cls

    for attr in dir(mod):
        obj = getattr(mod, attr)
        if isinstance(obj, type) and attr.endswith("Plugin"):
            return obj

    for attr in dir(mod):
        obj = getattr(mod, attr)
        if isinstance(obj, type) and hasattr(obj, "get_devices"):
            return obj

    raise ImportError(f"No plugin class found in micboard.integrations.{code}")
