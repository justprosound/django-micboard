"""
Polling orchestration service for django-micboard.

Coordinates device polling across all manufacturers, manages polling state,
and broadcasts updates via WebSocket/signals.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from django.utils import timezone

if TYPE_CHECKING:
    from micboard.models import Manufacturer

logger = logging.getLogger(__name__)


class PollingService:
    """
    Service for orchestrating device polling across manufacturers.

    Provides high-level API for triggering polls, checking health,
    and broadcasting results. Uses DeviceService internally for
    manufacturer-specific operations.
    """

    def __init__(self):
        """Initialize polling service."""
        pass

    def poll_all_manufacturers(self) -> dict[str, Any]:
        """
        Poll all active manufacturers.

        Returns:
            Dictionary with results per manufacturer
        """
        from micboard.models import Manufacturer

        manufacturers = Manufacturer.objects.filter(is_active=True)

        results = {
            "timestamp": timezone.now().isoformat(),
            "total_manufacturers": manufacturers.count(),
            "manufacturers": {},
            "summary": {
                "total_devices": 0,
                "total_transmitters": 0,
                "errors": [],
            },
        }

        for manufacturer in manufacturers:
            try:
                result = self.poll_manufacturer(manufacturer)
                results["manufacturers"][manufacturer.code] = result

                # Aggregate stats
                results["summary"]["total_devices"] += (
                    result.get("devices_created", 0) + result.get("devices_updated", 0)
                )
                results["summary"]["total_transmitters"] += result.get("transmitters_synced", 0)

                if result.get("errors"):
                    results["summary"]["errors"].extend(result["errors"])

            except Exception as e:
                error_msg = f"Failed to poll {manufacturer.name}: {e}"
                logger.exception(error_msg)
                results["summary"]["errors"].append(error_msg)
                results["manufacturers"][manufacturer.code] = {
                    "status": "failed",
                    "error": str(e),
                }

        logger.info(
            "Polling complete: %d manufacturers, %d devices, %d transmitters",
            results["total_manufacturers"],
            results["summary"]["total_devices"],
            results["summary"]["total_transmitters"],
        )

        return results

    def poll_manufacturer(self, manufacturer: Manufacturer) -> dict[str, Any]:
        """
        Poll a specific manufacturer for device updates.

        Args:
            manufacturer: Manufacturer instance

        Returns:
            Dictionary with polling results
        """
        from micboard.services.device_service import DeviceService

        logger.info("Starting poll for manufacturer: %s", manufacturer.name)

        try:
            # Use DeviceService for the heavy lifting
            service = DeviceService(manufacturer)
            result = service.poll_and_sync_all()

            # Broadcast updates if successful
            if not result.get("errors"):
                self.broadcast_device_updates(manufacturer, result)

            # Emit signal for monitoring
            self._emit_polling_signal(manufacturer, result)

            logger.info(
                "Poll complete for %s: %d devices, %d transmitters, %d errors",
                manufacturer.name,
                result.get("devices_created", 0) + result.get("devices_updated", 0),
                result.get("transmitters_synced", 0),
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
                "transmitters_synced": 0,
                "errors": [str(e)],
            }

    def broadcast_device_updates(self, manufacturer: Manufacturer, data: dict[str, Any]) -> None:
        """
        Broadcast device updates via WebSocket/Channels.

        Args:
            manufacturer: Manufacturer that was polled
            data: Polling result data
        """
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            from micboard.models import Receiver
            from micboard.serializers import ReceiverSummarySerializer
            from micboard.services.device_lifecycle import DeviceStatus

            channel_layer = get_channel_layer()
            if not channel_layer:
                logger.debug("No channel layer configured; skipping broadcast")
                return

            # Serialize receiver data for broadcast - use status field
            active_statuses = DeviceStatus.active_states()
            receivers = Receiver.objects.filter(manufacturer=manufacturer, status__in=active_statuses)
            serialized = ReceiverSummarySerializer(receivers, many=True).data

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
                "Broadcasted updates for %d devices from %s", len(serialized), manufacturer.name
            )

        except Exception:
            logger.exception("Failed to broadcast device updates for %s", manufacturer.name)

    def _emit_polling_signal(self, manufacturer: Manufacturer, data: dict[str, Any]) -> None:
        """
        Emit Django signal for polling completion.

        Args:
            manufacturer: Manufacturer that was polled
            data: Polling result data
        """
        try:
            from micboard.signals.broadcast_signals import devices_polled

            devices_polled.send(sender=self.__class__, manufacturer=manufacturer, data=data)

            logger.debug("Emitted devices_polled signal for %s", manufacturer.name)

        except Exception:
            logger.debug("Failed to emit devices_polled signal", exc_info=True)

    def get_polling_health(self) -> dict[str, Any]:
        """
        Check polling health status across all manufacturers.

        Returns:
            Dictionary with health status
        """
        from micboard.models import Manufacturer, Receiver
        from micboard.services.device_lifecycle import DeviceStatus

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

        online_statuses = {'online'}
        active_statuses = DeviceStatus.active_states()

        for manufacturer in manufacturers:
            receivers = Receiver.objects.filter(manufacturer=manufacturer)
            active_receivers = receivers.filter(status__in=active_statuses)
            online_receivers = active_receivers.filter(status__in=online_statuses)

            mfr_health = {
                "name": manufacturer.name,
                "total_devices": receivers.count(),
                "active_devices": active_receivers.count(),
                "online_devices": online_receivers.count(),
                "status": "healthy" if online_receivers.exists() else "warning",
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

    def check_api_health(self, manufacturer: Manufacturer) -> dict[str, Any]:
        """
        Check API health for a specific manufacturer.

        Args:
            manufacturer: Manufacturer to check

        Returns:
            Dictionary with health status
        """
        try:
            from micboard.manufacturers import get_manufacturer_plugin

            plugin_class = get_manufacturer_plugin(manufacturer.code)
            plugin = plugin_class(manufacturer)
            client = plugin.get_client()

            if hasattr(client, "check_health"):
                return cast(dict[str, Any], client.check_health())

            return {
                "status": "unknown",
                "message": "Health check not implemented for this manufacturer",
            }

        except Exception as e:
            logger.exception("Error checking API health for %s", manufacturer.name)
            return {
                "status": "error",
                "error": str(e),
            }


# Convenience function for quick access
def get_polling_service() -> PollingService:
    """
    Get a PollingService instance.

    Returns:
        PollingService instance
    """
    return PollingService()
