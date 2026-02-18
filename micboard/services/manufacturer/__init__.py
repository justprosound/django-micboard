"""Manufacturer integration services for django-micboard.

This package contains services for:
- Manufacturer-specific plugin management
- Manufacturer configuration and settings
- Plugin registry and discovery
"""

from __future__ import annotations

from .manufacturer import ManufacturerService
from .manufacturer_config_registry import ManufacturerConfig, ManufacturerConfigRegistry
from .plugin_registry import PluginRegistry

__all__ = [
    "ManufacturerConfig",
    "ManufacturerConfigRegistry",
    "ManufacturerService",
    "PluginRegistry",
]
