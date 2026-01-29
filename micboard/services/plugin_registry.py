"""Centralized plugin registry and loading service.

Provides a single point for plugin loading with caching, error handling,
and logging to reduce duplication across the codebase.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from micboard.manufacturers.base import ManufacturerPlugin

logger = logging.getLogger(__name__)
_plugin_cache: dict[str, type[ManufacturerPlugin]] = {}


class PluginRegistry:
    """Centralized registry for manufacturer plugin loading and caching."""

    @staticmethod
    def get_plugin_class(manufacturer_code: str) -> type[ManufacturerPlugin]:
        """Get plugin class by manufacturer code with caching.

        Args:
            manufacturer_code: Manufacturer code (e.g., 'shure', 'sennheiser').

        Returns:
            Plugin class implementing ManufacturerPlugin interface.

        Raises:
            ModuleNotFoundError: If plugin not found.
            ImportError: If plugin class not found in module.
        """
        # Check cache
        if manufacturer_code in _plugin_cache:
            return _plugin_cache[manufacturer_code]

        # Load plugin
        try:
            from micboard.manufacturers import get_manufacturer_plugin

            plugin_class = get_manufacturer_plugin(manufacturer_code)
            _plugin_cache[manufacturer_code] = plugin_class
            logger.debug(f"Loaded plugin for {manufacturer_code}")
            return plugin_class
        except (ModuleNotFoundError, ImportError) as e:
            logger.error(f"Failed to load plugin for {manufacturer_code}: {e}")
            raise

    @staticmethod
    def get_plugin(
        manufacturer_code: str, manufacturer: object | None = None
    ) -> ManufacturerPlugin | None:
        """Get plugin instance by manufacturer code.

        Args:
            manufacturer_code: Manufacturer code.
            manufacturer: Manufacturer model instance (optional).

        Returns:
            Plugin instance or None if not found.
        """
        try:
            plugin_class = PluginRegistry.get_plugin_class(manufacturer_code)

            # If no manufacturer provided, try to get from database
            if manufacturer is None:
                from micboard.models import Manufacturer

                try:
                    manufacturer = Manufacturer.objects.get(code=manufacturer_code)
                except Manufacturer.DoesNotExist:
                    manufacturer = None

            return plugin_class(manufacturer)
        except (ValueError, ModuleNotFoundError, ImportError) as e:
            logger.warning(f"Could not instantiate plugin for {manufacturer_code}: {e}")
            return None

    @staticmethod
    def clear_cache() -> None:
        """Clear plugin cache (useful for testing)."""
        global _plugin_cache
        _plugin_cache.clear()
        logger.debug("Plugin cache cleared")

    @staticmethod
    def get_all_active_plugins() -> list[ManufacturerPlugin]:
        """Get instances of all active manufacturer plugins.

        Returns:
            List of plugin instances for active manufacturers.
        """
        from micboard.models import Manufacturer

        plugins = []
        for manufacturer in Manufacturer.objects.filter(is_active=True):
            plugin = PluginRegistry.get_plugin(manufacturer.code, manufacturer)
            if plugin:
                plugins.append(plugin)
        return plugins
