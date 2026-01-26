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
        """Emit devices_polled signal after successful polling.

        Signal payload:
        {
            "manufacturer": Manufacturer instance,
            "manufacturer_code": str,
            "data": {
                "devices_created": int,
                "devices_updated": int,
                "units_synced": int,
                "errors": list[str],
                ...
            }
        }

        Args:
            manufacturer: Manufacturer that was polled
            data: Polling result dict
            async_emit: If True, emit asynchronously
        """
        try:
            from micboard.signals.broadcast_signals import devices_polled

            payload = {
                "manufacturer": manufacturer,
                "manufacturer_code": manufacturer.code,
                "data": data,
            }

            if async_emit:
                try:
                    from asgiref.sync import async_to_sync

                    async_to_sync(SignalEmitter._emit_async)(devices_polled, SignalEmitter, payload)
                except Exception:
                    logger.exception("Failed to emit devices_polled signal asynchronously")
                    # Fall back to synchronous
                    devices_polled.send(sender=SignalEmitter, **payload)
            else:
                devices_polled.send(sender=SignalEmitter, **payload)

            logger.debug(
                "Emitted devices_polled signal for %s",
                manufacturer.name,
            )

        except Exception:
            logger.exception(
                "Failed to emit devices_polled signal for %s",
                manufacturer.name,
            )

    @staticmethod
    def emit_api_health_changed(
        manufacturer: Manufacturer,
        health_data: dict[str, Any],
        *,
        previous_status: str | None = None,
    ) -> None:
        """Emit api_health_changed signal when API health status changes.

        Signal payload:
        {
            "manufacturer": Manufacturer instance,
            "manufacturer_code": str,
            "health_data": {
                "status": "healthy" | "degraded" | "unhealthy",
                "timestamp": ISO string,
                "details": {...}
            },
            "previous_status": str or None
        }

        Args:
            manufacturer: Manufacturer whose API was checked
            health_data: Standardized health check result
            previous_status: Previous health status (for change detection)
        """
        try:
            from micboard.signals.broadcast_signals import api_health_changed

            payload = {
                "manufacturer": manufacturer,
                "manufacturer_code": manufacturer.code,
                "health_data": health_data,
            }

            if previous_status:
                payload["previous_status"] = previous_status

            api_health_changed.send(sender=SignalEmitter, **payload)

            logger.debug(
                "Emitted api_health_changed signal for %s: %s",
                manufacturer.name,
                health_data.get("status"),
            )

        except Exception:
            logger.exception(
                "Failed to emit api_health_changed signal for %s",
                manufacturer.name,
            )

    @staticmethod
    def emit_device_status_changed(
        device_id: int,
        old_status: str,
        new_status: str,
        *,
        device_name: str | None = None,
        manufacturer: Manufacturer | None = None,
    ) -> None:
        """Emit device_status_changed signal when device status changes.

        Signal payload:
        {
            "device_id": int,
            "device_name": str or None,
            "old_status": str,
            "new_status": str,
            "manufacturer": Manufacturer or None,
            "manufacturer_code": str or None
        }

        Args:
            device_id: Device ID
            old_status: Previous status
            new_status: New status
            device_name: Optional device name
            manufacturer: Optional manufacturer
        """
        try:
            from micboard.signals.broadcast_signals import device_status_changed

            payload = {
                "device_id": device_id,
                "old_status": old_status,
                "new_status": new_status,
            }

            if device_name:
                payload["device_name"] = device_name
            if manufacturer:
                payload["manufacturer"] = manufacturer
                payload["manufacturer_code"] = manufacturer.code

            device_status_changed.send(sender=SignalEmitter, **payload)

            logger.debug(
                "Emitted device_status_changed signal for device %s: %s → %s",
                device_id,
                old_status,
                new_status,
            )

        except Exception:
            logger.exception(
                "Failed to emit device_status_changed signal for device %s",
                device_id,
            )

    @staticmethod
    def emit_sync_completed(
        manufacturer: Manufacturer,
        result: dict[str, Any],
    ) -> None:
        """Emit sync_completed signal after device sync completes.

        Signal payload:
        {
            "manufacturer": Manufacturer instance,
            "manufacturer_code": str,
            "result": {
                "devices_created": int,
                "devices_updated": int,
                "errors": list[str],
                ...
            }
        }

        Args:
            manufacturer: Manufacturer that was synced
            result: Sync result dict
        """
        try:
            from micboard.signals.broadcast_signals import sync_completed

            payload = {
                "manufacturer": manufacturer,
                "manufacturer_code": manufacturer.code,
                "result": result,
            }

            sync_completed.send(sender=SignalEmitter, **payload)

            logger.debug(
                "Emitted sync_completed signal for %s",
                manufacturer.name,
            )

        except Exception:
            logger.exception(
                "Failed to emit sync_completed signal for %s",
                manufacturer.name,
            )

    @staticmethod
    def emit_discovery_approved(
        queue_item_id: int,
        manufacturer_code: str,
        device_count: int,
    ) -> None:
        """Emit discovery_approved signal when devices are approved from queue.

        Signal payload:
        {
            "queue_item_id": int,
            "manufacturer_code": str,
            "device_count": int
        }

        Args:
            queue_item_id: DiscoveryQueue item ID
            manufacturer_code: Manufacturer code
            device_count: Number of devices approved
        """
        try:
            from micboard.signals.broadcast_signals import discovery_approved

            payload = {
                "queue_item_id": queue_item_id,
                "manufacturer_code": manufacturer_code,
                "device_count": device_count,
            }

            discovery_approved.send(sender=SignalEmitter, **payload)

            logger.debug(
                "Emitted discovery_approved signal for queue item %s: %d devices",
                queue_item_id,
                device_count,
            )

        except Exception:
            logger.exception(
                "Failed to emit discovery_approved signal for queue item %s",
                queue_item_id,
            )

    @staticmethod
    def emit_error(
        error_type: str,
        error_message: str,
        *,
        manufacturer: Manufacturer | None = None,
        device_id: int | None = None,
    ) -> None:
        """Emit error signal for notable errors.

        Signal payload:
        {
            "error_type": str,
            "error_message": str,
            "manufacturer": Manufacturer or None,
            "device_id": int or None,
            "timestamp": ISO string
        }

        Args:
            error_type: Type of error (e.g., "api_error", "sync_error")
            error_message: Error message
            manufacturer: Optional manufacturer
            device_id: Optional device ID
        """
        try:
            from django.utils import timezone

            from micboard.signals.broadcast_signals import error_occurred

            payload = {
                "error_type": error_type,
                "error_message": error_message,
                "timestamp": timezone.now().isoformat(),
            }

            if manufacturer:
                payload["manufacturer"] = manufacturer
                payload["manufacturer_code"] = manufacturer.code
            if device_id:
                payload["device_id"] = device_id

            error_occurred.send(sender=SignalEmitter, **payload)

            logger.debug(
                "Emitted error signal: %s - %s",
                error_type,
                error_message,
            )

        except Exception:
            logger.exception(
                "Failed to emit error signal for %s",
                error_type,
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
