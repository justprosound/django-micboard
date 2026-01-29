"""Polling service layer for orchestrating device telemetry updates.

Coordinates periodic status updates from manufacturer APIs and updates
local hardware/RF channel models. This is a low-level polling service
for direct API interaction; use polling_service.py for high-level orchestration.
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from micboard.models import ManufacturerAPIServer, WirelessChassis
from micboard.services.hardware import HardwareService

logger = logging.getLogger(__name__)


class PollingService:
    """Business logic for direct API server device status polling.

    This service handles low-level polling of manufacturer API servers.
    For high-level polling orchestration and broadcasting, see polling_service.py.
    """

    @staticmethod
    def poll_all_active_devices() -> dict[str, int]:
        """Trigger polling for all active devices across all configured APIs.

        Returns:
            Dictionary with success and failed counts
        """
        # 1. Get all enabled API servers
        api_servers = ManufacturerAPIServer.objects.filter(enabled=True)
        results = {"success": 0, "failed": 0}

        for server in api_servers:
            try:
                PollingService.poll_server_devices(server)
                results["success"] += 1
            except Exception as e:
                logger.error(f"Failed to poll API server {server.name}: {e}")
                results["failed"] += 1

        return results

    @staticmethod
    def poll_server_devices(server: ManufacturerAPIServer) -> None:
        """Poll specific API server and update related devices.

        Args:
            server: ManufacturerAPIServer instance to poll

        Raises:
            Exception: If poll fails (sets server status to ERROR)
        """
        from micboard.services.plugin_registry import PluginRegistry

        # Get manufacturer plugin for this server
        try:
            plugin = PluginRegistry.get_plugin(server.manufacturer)
        except Exception as e:
            logger.debug(f"Plugin not found for {server.manufacturer}: {e}")
            return

        if not plugin:
            logger.error(f"Plugin not available for {server.manufacturer}")
            return

        # Get current state from API
        try:
            api_devices = plugin.get_devices()

            for dev_data in api_devices:
                serial = dev_data.get("serial") or dev_data.get("serialNumber")
                if not serial:
                    continue

                # Find local chassis
                chassis = WirelessChassis.objects.filter(serial_number=serial).first()
                if not chassis:
                    continue

                # Update status
                is_online = dev_data.get("state") == "ONLINE"
                HardwareService.sync_hardware_status(obj=chassis, online=is_online)

                chassis.last_seen = timezone.now()
                chassis.save(update_fields=["last_seen"])

            # Update server health
            server.status = ManufacturerAPIServer.Status.ACTIVE
            server.last_health_check = timezone.now()
            server.save(update_fields=["status", "last_health_check"])

        except Exception as e:
            server.status = ManufacturerAPIServer.Status.ERROR
            server.status_message = str(e)[:200]
            server.save(update_fields=["status", "status_message"])
            raise

    @staticmethod
    def get_server_status(server: ManufacturerAPIServer) -> dict[str, Any]:
        """Get current status of an API server.

        Args:
            server: ManufacturerAPIServer instance

        Returns:
            Dictionary with server status details
        """
        return {
            "name": server.name,
            "manufacturer": server.manufacturer,
            "status": server.status,
            "enabled": server.enabled,
            "last_health_check": server.last_health_check,
            "status_message": server.status_message,
            "base_url": server.base_url,
        }

    @staticmethod
    def get_all_server_statuses() -> dict[str, Any]:
        """Get status of all API servers.

        Returns:
            Dictionary with statuses for all configured servers
        """
        servers = ManufacturerAPIServer.objects.all()
        return {
            "total": servers.count(),
            "enabled": servers.filter(enabled=True).count(),
            "active": servers.filter(status="active").count(),
            "error": servers.filter(status="error").count(),
            "servers": [PollingService.get_server_status(s) for s in servers],
        }
