"""Polling orchestration service for django-micboard.

Coordinates one manufacturer poll and broadcasts its persisted device state.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from micboard.services.sync.polling_dtos import ManufacturerPollLimits

if TYPE_CHECKING:  # pragma: no cover
    from micboard.models.discovery.manufacturer import Manufacturer

logger = logging.getLogger(__name__)


class PollingService:
    """Orchestrate the supported single-manufacturer polling path."""

    def poll_manufacturer(
        self,
        manufacturer: Manufacturer,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        """Poll a specific manufacturer for hardware updates.

        Args:
            manufacturer: Manufacturer instance
            force: Permit an explicitly requested operator poll while inactive.

        Returns:
            Dictionary with polling results
        """
        from micboard.services.sync.hardware_sync_service import HardwareSyncService

        logger.info("Starting poll for manufacturer: %s", manufacturer.name)

        try:
            # Use HardwareSyncService for the heavy lifting
            stats = HardwareSyncService.sync_devices(
                manufacturer_code=manufacturer.code,
                force=force,
            )

            # Map stats back to result format
            error_count = int(stats.get("errors", 0))
            result: dict[str, Any] = {
                "devices_created": stats.get("created", 0),
                "devices_updated": stats.get("updated", 0),
                "units_synced": 0,  # HardwareSyncService doesn't track units yet
                "errors": ["Manufacturer sync reported errors"] if error_count else [],
                "devices_examined": stats.get("devices_examined", 0),
                "device_limit": stats.get("device_limit"),
                "inventory_complete": stats.get("inventory_complete", True),
            }

            # Broadcast updates if successful
            if not result.get("errors"):
                self.broadcast_device_updates(manufacturer, result)

            logger.info(
                "Poll complete for %s: %d chassis, %d units, %d errors",
                manufacturer.name,
                result.get("devices_created", 0) + result.get("devices_updated", 0),
                result.get("units_synced", 0),
                len(result.get("errors", [])),
            )

            return result

        except Exception as exc:
            from micboard.utils.exception_logging import sanitized_exception_info

            logger.exception(
                "Polling failed for manufacturer %s",
                manufacturer.code,
                exc_info=sanitized_exception_info(exc),
            )
            error_message = f"{type(exc).__name__}: polling failed"
            return {
                "manufacturer": manufacturer.code,
                "status": "failed",
                "error": error_message,
                "devices_created": 0,
                "devices_updated": 0,
                "units_synced": 0,
                "errors": [error_message],
            }

    def broadcast_device_updates(self, manufacturer: Manufacturer, data: dict[str, Any]) -> None:
        """Broadcast device updates via WebSocket/Channels.

        Args:
            manufacturer: Manufacturer that was polled
            data: Polling result data
        """
        try:
            from micboard.services.notification.device_broadcast_service import (
                DeviceSnapshotBroadcastService,
            )

            # Serialize chassis data for broadcast - use status field
            # Active states: online, degraded, provisioning
            active_statuses = ["online", "degraded", "provisioning"]
            limits = ManufacturerPollLimits.from_settings()
            result = DeviceSnapshotBroadcastService.broadcast(
                manufacturer=manufacturer,
                namespace="poll",
                max_devices=limits.max_devices,
                chunk_size=limits.broadcast_chunk_size,
                statuses=active_statuses,
            )

            logger.debug(
                "Broadcasted %d bounded chunks for %d chassis from %s",
                result.chunks_sent,
                result.rows_sent,
                manufacturer.pk,
            )

        except Exception as exc:
            from micboard.utils.exception_logging import sanitized_exception_info

            logger.exception(
                "Failed to broadcast device updates for manufacturer %s",
                manufacturer.pk,
                exc_info=sanitized_exception_info(exc),
            )
