"""Compatibility shim package for manufacturer plugins.

This package preserves the historic `micboard.manufacturers` import paths while
delegating implementations to `micboard.integrations`. It exposes a
`get_manufacturer_plugin(code)` helper and re-maps available integration
packages so imports like `micboard.manufacturers.shure.client` continue to work.

Don't add new manufacturer implementations here — place them under
`micboard.integrations.<manufacturer>`.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from types import ModuleType
from typing import Any, cast

from .base import BaseAPIClient, BasePlugin, ManufacturerPlugin

__all__ = ["BaseAPIClient", "BasePlugin", "ManufacturerPlugin", "get_manufacturer_plugin"]


def get_manufacturer_plugin(code: str) -> type[ManufacturerPlugin]:
    """Return the plugin class for a manufacturer code.

    This function attempts to import `micboard.integrations.<code>.plugin` and
    locate the plugin class. It prefers a class named <CodeTitle>Plugin, then
    falls back to the first exported class whose name ends with 'Plugin' or
    which implements a `get_devices` method.
    """
    code = str(code)
    # Try to import the plugin module under integrations
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

    # Common class name: ShurePlugin, SennheiserPlugin, etc.
    candidate_name = "".join(part.capitalize() for part in code.split("_")) + "Plugin"
    if hasattr(mod, candidate_name):
        cls = getattr(mod, candidate_name)
        if isinstance(cls, type):
            return cls

    # Otherwise, search for a class that looks like a Plugin
    for attr in dir(mod):
        obj = getattr(mod, attr)
        if isinstance(obj, type) and attr.endswith("Plugin"):
            return obj

    # Last-resort heuristic: any class that defines get_devices
    for attr in dir(mod):
        obj = getattr(mod, attr)
        if isinstance(obj, type) and hasattr(obj, "get_devices"):
            return obj

    raise ImportError(f"No plugin class found in micboard.integrations.{code}")


# Mirror integration packages under micboard.manufacturers so existing imports
# like `micboard.manufacturers.shure.client` continue to resolve. We import
# the integration package and inject it into sys.modules under the
# `micboard.manufacturers.<name>` key.
integrations_pkg: ModuleType | None = None
try:
    integrations_pkg = importlib.import_module("micboard.integrations")
except ModuleNotFoundError:
    integrations_pkg = None

if integrations_pkg is not None:
    for _finder, name, _ispkg in pkgutil.iter_modules(integrations_pkg.__path__):
        try:
            pkg = importlib.import_module(f"micboard.integrations.{name}")
        except Exception:
            # If importing an individual integration fails, skip it. Tests may
            # explicitly import the module they need and will report failures.
            continue

        mapped_name = f"{__name__}.{name}"
        # Place the integration package object into sys.modules under the
        # manufacturers subpackage name so that submodule imports resolve.
        if isinstance(pkg, ModuleType):
            sys.modules[mapped_name] = pkg
            # Also expose as attribute on this package for convenience
            setattr(sys.modules[__name__], name, pkg)
