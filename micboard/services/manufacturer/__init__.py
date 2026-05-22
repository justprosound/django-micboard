"""Manufacturer integration services for django-micboard.

This package contains services for:
- Manufacturer-specific plugin management
- Manufacturer configuration and settings
- Plugin registry and discovery
"""

from __future__ import annotations

from .config import apply_manufacturer_config, validate_manufacturer_config
from .manufacturer_config_registry import ManufacturerConfig, ManufacturerConfigRegistry
from .plugin_registry import PluginRegistry
from .query import ManufacturerQueryService
from .signals import (
    delete_manufacturer,
    handle_manufacturer_delete,
    handle_manufacturer_save,
    save_manufacturer,
)
from .sync import ManufacturerSyncService

__all__ = [
    "ManufacturerConfig",
    "ManufacturerConfigRegistry",
    "ManufacturerQueryService",
    "ManufacturerSyncService",
    "PluginRegistry",
    "apply_manufacturer_config",
    "delete_manufacturer",
    "handle_manufacturer_delete",
    "handle_manufacturer_save",
    "save_manufacturer",
    "validate_manufacturer_config",
]
