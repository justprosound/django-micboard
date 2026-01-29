"""Signal emission utilities for django-micboard.

Centralizes all signal emission to ensure consistency, proper error handling,
and standardized payload formats.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from micboard.models import Manufacturer

logger = logging.getLogger(__name__)


class SignalEmitter:
    """Centralized signal emission utility.

    Use this instead of directly calling signal.send() to ensure:
    1. Consistent sender (always SignalEmitter)
    2. Standardized payload format
    3. Proper error handling and logging
    4. Optional async emission
    """

    @staticmethod
    def emit_devices_polled(
        manufacturer: Manufacturer,
        data: dict[str, Any],
        *,
        async_emit: bool = False,
    ) -> None:
        """Broadcast device polled event (replacing signals)."""
        try:
            from channels.layers import get_channel_layer

            if get_channel_layer():
                from micboard.services.broadcast_service import BroadcastService

                BroadcastService.broadcast_device_update(manufacturer=manufacturer, data=data)
        except ImportError:
            logger.debug("Channels not available, skipping broadcast for device update")

    @staticmethod
    def emit_api_health_changed(
        manufacturer: Manufacturer,
        health_data: dict[str, Any],
        *,
        previous_status: str | None = None,
    ) -> None:
        """Broadcast API health change (replacing signals)."""
        try:
            from channels.layers import get_channel_layer

            if get_channel_layer():
                from micboard.services.broadcast_service import BroadcastService

                BroadcastService.broadcast_api_health(
                    manufacturer=manufacturer, health_data=health_data
                )
        except ImportError:
            logger.debug("Channels not available, skipping broadcast for API health change")

    @staticmethod
    def emit_device_status_changed(
        device_id: int,
        old_status: str,
        new_status: str,
        *,
        device_name: str | None = None,
        manufacturer: Manufacturer | None = None,
    ) -> None:
        """Broadcast device status change (replacing signals)."""
        from micboard.services.broadcast_service import BroadcastService

        BroadcastService.broadcast_device_status(
            service_code=manufacturer.code if manufacturer else "unknown",
            device_id=device_id,
            device_type="Unknown",  # Model type not easily available here
            status=new_status,
            is_active=new_status == "online",
        )

    @staticmethod
    def emit_sync_completed(
        manufacturer: Manufacturer,
        result: dict[str, Any],
    ) -> None:
        """Broadcast sync completion (replacing signals)."""
        from micboard.services.broadcast_service import BroadcastService

        BroadcastService.broadcast_sync_completion(
            service_code=manufacturer.code,
            sync_result=result,
        )

    @staticmethod
    def emit_discovery_approved(
        queue_item_id: int,
        manufacturer_code: str,
        device_count: int,
    ) -> None:
        """Broadcast discovery approval (replacing signals)."""
        from micboard.services.broadcast_service import BroadcastService

        BroadcastService.broadcast_discovery_approved(
            queue_item_id=queue_item_id,
            manufacturer_code=manufacturer_code,
            device_count=device_count,
        )

    @staticmethod
    def emit_error(
        error_type: str,
        error_message: str,
        *,
        manufacturer: Manufacturer | None = None,
        device_id: int | None = None,
    ) -> None:
        """Broadcast error notification (replacing signals)."""
        from micboard.services.broadcast_service import BroadcastService

        BroadcastService.broadcast_error(
            error_type=error_type,
            error_message=error_message,
            manufacturer_code=manufacturer.code if manufacturer else None,
            device_id=device_id,
        )

    @staticmethod
    async def _emit_async(signal, sender, payload):
        """Helper for async signal emission."""
        signal.send(sender=sender, **payload)


# Convenience functions for common patterns
def emit_polling_complete(
    manufacturer: Manufacturer,
    created: int,
    updated: int,
    errors: list[str] | None = None,
) -> None:
    """Convenience function to emit polling complete signal.

    Args:
        manufacturer: Manufacturer that was polled
        created: Number of chassis created
        updated: Number of chassis updated
        errors: List of errors (if any)
    """
    data = {
        "devices_created": created,
        "devices_updated": updated,
        "units_synced": 0,
        "errors": errors or [],
    }
    SignalEmitter.emit_devices_polled(manufacturer, data)


def emit_health_status(
    manufacturer: Manufacturer,
    status: str,
    previous_status: str | None = None,
) -> None:
    """Convenience function to emit health status signal.

    Args:
        manufacturer: Manufacturer
        status: Health status (healthy, degraded, unhealthy, error)
        previous_status: Previous status
    """
    from django.utils import timezone

    health_data = {
        "status": status,
        "timestamp": timezone.now().isoformat(),
    }
    SignalEmitter.emit_api_health_changed(
        manufacturer, health_data, previous_status=previous_status
    )
