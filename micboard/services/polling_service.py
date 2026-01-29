"""Polling orchestration service for django-micboard.

Coordinates device polling across all manufacturers, manages polling state,
and broadcasts updates via WebSocket/signals.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from micboard.services.base_polling_mixin import PollingMixin

if TYPE_CHECKING:  # pragma: no cover
    from micboard.models import Manufacturer

logger = logging.getLogger(__name__)


class PollingService(PollingMixin):
    """Service for orchestrating device polling across manufacturers.

    Provides high-level API for triggering polls, checking health,
    and broadcasting results. Uses HardwareService internally for
    manufacturer-specific operations.
    """

    def __init__(self):
        """Initialize polling service."""
        pass

    def refresh_devices(self, *, manufacturer: str | None = None) -> dict[str, Any]:
        """Refresh device data by invoking the standard polling pipeline.

        Args:
            manufacturer: Optional manufacturer code to scope the refresh. If omitted,
                all manufacturers are refreshed.

        Returns:
            Mapping of manufacturer code to refresh summary including status and counts.
        """
        from micboard.models import Manufacturer

        results: dict[str, dict[str, Any]] = {}
        queryset = (
            Manufacturer.objects.filter(code=manufacturer)
            if manufacturer
            else Manufacturer.objects.all()
        )

        for mfr in queryset:
            poll_result = self.poll_manufacturer(mfr)
            device_count = poll_result.get("devices_created", 0) + poll_result.get(
                "devices_updated", 0
            )
            has_errors = bool(poll_result.get("errors")) or poll_result.get("status") == "failed"

            results[mfr.code] = {
                "status": "error" if has_errors else "success",
                "device_count": device_count,
                "updated": device_count,
                "errors": poll_result.get("errors", []),
            }

        return results

    def poll_all_manufacturers(self) -> dict[str, Any]:
        """Poll all active manufacturers using centralized mixin logic.

        Returns:
            Dictionary with results per manufacturer
        """
        return self.poll_all_manufacturers_with_handler(
            on_manufacturer_polled=self._poll_manufacturer_handler,
            on_complete=self._on_polling_complete,
        )

    def _poll_manufacturer_handler(self, manufacturer: Manufacturer) -> dict[str, Any]:
        """Handler invoked by mixin for each manufacturer."""
        return self.poll_manufacturer(manufacturer)

    def poll_manufacturer(self, manufacturer: Manufacturer) -> dict[str, Any]:
        """Poll a specific manufacturer for hardware updates.

        Args:
            manufacturer: Manufacturer instance

        Returns:
            Dictionary with polling results
        """
        from micboard.services.hardware_sync_service import HardwareSyncService
        from micboard.services.signal_emitter import SignalEmitter

        logger.info("Starting poll for manufacturer: %s", manufacturer.name)

        try:
            # Use HardwareSyncService for the heavy lifting
            stats = HardwareSyncService.sync_devices(manufacturer_code=manufacturer.code)

            # Map stats back to result format
            result = {
                "devices_created": stats.get("created", 0),
                "devices_updated": stats.get("updated", 0),
                "units_synced": 0,  # HardwareSyncService doesn't track units yet
                "errors": stats.get("error_messages", []),
            }

            # Broadcast updates if successful
            if not result.get("errors"):
                self.broadcast_device_updates(manufacturer, result)

            # Emit signal using centralized SignalEmitter
            SignalEmitter.emit_devices_polled(manufacturer, result)

            logger.info(
                "Poll complete for %s: %d chassis, %d units, %d errors",
                manufacturer.name,
                result.get("devices_created", 0) + result.get("devices_updated", 0),
                result.get("units_synced", 0),
                len(result.get("errors", [])),
            )

            return result

        except Exception as e:
            error_msg = f"Polling failed for {manufacturer.name}: {e}"
            logger.exception(error_msg)
            return {
                "manufacturer": manufacturer.code,
                "status": "failed",
                "error": str(e),
                "devices_created": 0,
                "devices_updated": 0,
                "units_synced": 0,
                "errors": [str(e)],
            }

    def _on_polling_complete(self, results: dict[str, Any]) -> None:
        """Callback invoked after all manufacturers are polled."""
        # Could run alerts, cleanup, etc.
        logger.debug(
            "Polling sequence completed: %d manufacturers",
            results.get("total_manufacturers"),
        )

    def broadcast_device_updates(self, manufacturer: Manufacturer, data: dict[str, Any]) -> None:
        """Broadcast device updates via WebSocket/Channels.

        Args:
            manufacturer: Manufacturer that was polled
            data: Polling result data
        """
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            from micboard.models import WirelessChassis
            from micboard.services.hardware_lifecycle import HardwareStatus

            channel_layer = get_channel_layer()
            if not channel_layer:
                logger.debug("No channel layer configured; skipping broadcast")
                return

            # Serialize chassis data for broadcast - use status field
            active_statuses = HardwareStatus.active_states()
            chassis_qs = WirelessChassis.objects.filter(
                manufacturer=manufacturer, status__in=active_statuses
            )
            serialized = [
                {
                    "id": chassis.id,
                    "api_device_id": chassis.api_device_id,
                    "name": chassis.name,
                    "ip": str(chassis.ip) if chassis.ip else None,
                    "status": chassis.status,
                    "model": chassis.model,
                }
                for chassis in chassis_qs
            ]

            # Send to WebSocket group
            async_to_sync(channel_layer.group_send)(
                "micboard_updates",
                {
                    "type": "device_update",
                    "manufacturer_code": manufacturer.code,
                    "receivers": serialized,
                    "timestamp": timezone.now().isoformat(),
                },
            )

            logger.debug(
                "Broadcasted updates for %d chassis from %s", len(serialized), manufacturer.name
            )

        except Exception:
            logger.exception("Failed to broadcast device updates for %s", manufacturer.name)

    def check_api_health(self, manufacturer: Manufacturer) -> dict[str, Any]:
        """Check API health for a specific manufacturer.

        Uses centralized health response standardization and signal emission.

        Args:
            manufacturer: Manufacturer to check

        Returns:
            Dictionary with standardized health status
        """
        from micboard.manufacturers import get_manufacturer_plugin
        from micboard.services.signal_emitter import SignalEmitter

        try:
            plugin_class = get_manufacturer_plugin(manufacturer.code)
            plugin = plugin_class(manufacturer)
            client = plugin.get_client()

            if hasattr(client, "check_health"):
                raw_health = client.check_health()
            else:
                raw_health = {
                    "status": "unknown",
                    "message": "Health check not implemented for this manufacturer",
                }

            # Standardize the response format
            standardized = self._standardize_health_response(raw_health)

            # Emit signal using centralized SignalEmitter
            SignalEmitter.emit_api_health_changed(manufacturer, standardized)

            return standardized

        except Exception as e:
            logger.exception("Error checking API health for %s", manufacturer.name)
            error_response = self._standardize_health_response({"status": "error", "error": str(e)})
            # Still emit signal for error status
            SignalEmitter.emit_api_health_changed(manufacturer, error_response)
            return error_response

    def get_polling_health(self) -> dict[str, Any]:
        """Check polling health status across all manufacturers.

        Returns:
            Dictionary with health status
        """
        from micboard.models import Manufacturer, WirelessChassis
        from micboard.services.hardware_lifecycle import HardwareStatus

        manufacturers = Manufacturer.objects.filter(is_active=True)

        health = {
            "timestamp": timezone.now().isoformat(),
            "overall_status": "healthy",
            "manufacturers": {},
            "summary": {
                "total_devices": 0,
                "online_devices": 0,
                "offline_devices": 0,
            },
        }

        online_statuses = {"online"}
        active_statuses = HardwareStatus.active_states()

        for manufacturer in manufacturers:
            chassis_qs = WirelessChassis.objects.filter(manufacturer=manufacturer)
            active_chassis = chassis_qs.filter(status__in=active_statuses)
            online_chassis = active_chassis.filter(status__in=online_statuses)

            mfr_health = {
                "name": manufacturer.name,
                "total_devices": chassis_qs.count(),
                "active_devices": active_chassis.count(),
                "online_devices": online_chassis.count(),
                "status": "healthy" if online_chassis.exists() else "warning",
            }

            # Check API client health
            try:
                from micboard.manufacturers import get_manufacturer_plugin

                plugin_class = get_manufacturer_plugin(manufacturer.code)
                plugin = plugin_class(manufacturer)
                client = plugin.get_client()

                if hasattr(client, "is_healthy"):
                    api_healthy = client.is_healthy()
                    mfr_health["api_status"] = "healthy" if api_healthy else "unhealthy"

                    if not api_healthy:
                        mfr_health["status"] = "unhealthy"
                        health["overall_status"] = "degraded"

            except Exception as e:
                mfr_health["api_status"] = "error"
                mfr_health["api_error"] = str(e)
                mfr_health["status"] = "unhealthy"
                health["overall_status"] = "degraded"

            health["manufacturers"][manufacturer.code] = mfr_health

            # Update summary
            health["summary"]["total_devices"] += mfr_health["total_devices"]
            health["summary"]["online_devices"] += mfr_health["online_devices"]
            health["summary"]["offline_devices"] += (
                mfr_health["total_devices"] - mfr_health["online_devices"]
            )

        return health


# Convenience function for quick access
def get_polling_service() -> PollingService:
    """Get a PollingService instance.

    Returns:
        PollingService instance
    """
    return PollingService()
