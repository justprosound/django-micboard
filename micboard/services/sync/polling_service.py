"""Polling orchestration service for django-micboard.

Coordinates one manufacturer poll and broadcasts its persisted device state.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from micboard.services.manufacturer.sync import ManufacturerSyncService
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
        logger.info("Starting poll for manufacturer: %s", manufacturer.name)
        started_at = timezone.now()

        try:
            sync_result = ManufacturerSyncService.sync_devices_for_manufacturer(
                manufacturer_code=manufacturer.code,
                force=force,
            )

            result: dict[str, Any] = {
                "devices_created": sync_result.get("devices_added", 0),
                "devices_updated": sync_result.get("devices_updated", 0),
                "units_synced": 0,
                "errors": list(sync_result.get("errors", [])),
                "devices_examined": sync_result.get("devices_examined", 0),
                "device_limit": sync_result.get("device_limit"),
                "inventory_complete": sync_result.get("inventory_complete", True),
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

            self._record_sync_audit(
                manufacturer=manufacturer,
                started_at=started_at,
                result=result,
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
            result = {
                "manufacturer": manufacturer.code,
                "status": "failed",
                "error": error_message,
                "devices_created": 0,
                "devices_updated": 0,
                "units_synced": 0,
                "errors": [error_message],
            }
            self._record_sync_audit(
                manufacturer=manufacturer,
                started_at=started_at,
                result=result,
            )
            return result

    @staticmethod
    def _record_sync_audit(
        *,
        manufacturer: Manufacturer,
        started_at: datetime,
        result: dict[str, Any],
    ) -> None:
        """Delegate bounded audit persistence without widening poll orchestration."""
        from micboard.services.maintenance.sync_audit_service import ServiceSyncAuditService

        ServiceSyncAuditService.record_poll_result(
            manufacturer=manufacturer,
            started_at=started_at,
            result=result,
        )

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
