"""Query operations for manufacturer data.

Read-only operations for retrieving manufacturer plugins,
configurations, device status, and connection health.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db.models import QuerySet

from micboard.models.discovery.configuration import ManufacturerConfiguration
from micboard.services.manufacturer.plugin_registry import PluginRegistry

if TYPE_CHECKING:
    from micboard.services.common.base import ManufacturerPlugin

logger = logging.getLogger(__name__)


class ManufacturerQueryService:
    """Read-only operations for manufacturer API interactions."""

    @staticmethod
    def get_plugin(*, manufacturer_code: str) -> ManufacturerPlugin | None:
        """Retrieve a manufacturer plugin by code.

        Args:
            manufacturer_code: Manufacturer code (e.g., 'shure', 'sennheiser').

        Returns:
            ManufacturerPlugin instance or None if not found.
        """
        return PluginRegistry.get_plugin(manufacturer_code)

    @staticmethod
    def get_active_manufacturers() -> QuerySet:
        """Get all active manufacturer configurations.

        Returns:
            QuerySet of active ManufacturerConfiguration objects.
        """
        return ManufacturerConfiguration.objects.filter(is_active=True)

    @staticmethod
    def get_manufacturer_config(*, manufacturer_code: str) -> ManufacturerConfiguration | None:
        """Get configuration for a manufacturer.

        Args:
            manufacturer_code: Manufacturer code.

        Returns:
            ManufacturerConfiguration object or None.
        """
        return ManufacturerConfiguration.objects.filter(
            code=manufacturer_code, is_active=True
        ).first()

    @staticmethod
    def test_manufacturer_connection(*, manufacturer_code: str) -> dict[str, Any]:
        """Test connectivity to a manufacturer API.

        Args:
            manufacturer_code: Manufacturer code.

        Returns:
            Dictionary with test result:
            {
                'success': bool,
                'message': str,
                'response_time_ms': float | None
            }
        """
        plugin = ManufacturerQueryService.get_plugin(manufacturer_code=manufacturer_code)
        if not plugin:
            return {
                "success": False,
                "message": f"Plugin not found: {manufacturer_code}",
                "response_time_ms": None,
            }

        try:
            result = plugin.test_connection()  # type: ignore[attr-defined]
            return result
        except Exception as e:
            return {"success": False, "message": str(e), "response_time_ms": None}

    @staticmethod
    def get_device_status(*, manufacturer_code: str, device_id: str) -> dict[str, Any] | None:
        """Get status of a specific device from manufacturer API.

        Args:
            manufacturer_code: Manufacturer code.
            device_id: Device ID in manufacturer system.

        Returns:
            Device status dict or None if not found/error.
        """
        plugin = ManufacturerQueryService.get_plugin(manufacturer_code=manufacturer_code)
        if not plugin:
            return None

        try:
            return plugin.get_device_status(device_id)  # type: ignore[attr-defined]
        except Exception:
            return None

    @staticmethod
    async def aget_manufacturer_config(*, manufacturer_code: str):
        """Async: Get manufacturer configuration.

        Args:
            manufacturer_code: Manufacturer code

        Returns:
            ManufacturerConfiguration instance or None
        """
        from asgiref.sync import sync_to_async

        return await sync_to_async(ManufacturerQueryService.get_manufacturer_config)(
            manufacturer_code=manufacturer_code
        )
