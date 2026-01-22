"""
Minimal signal handlers for device lifecycle events.

IMPORTANT: Business logic moved to DeviceLifecycleManager.
These handlers ONLY handle:
- WebSocket broadcasting for real-time UI updates
- Minimal event logging for audit trail

All state transitions, validation, and sync logic is in:
- micboard.services.device_lifecycle.DeviceLifecycleManager
- micboard.services.manufacturer_service.ManufacturerService
"""

from __future__ import annotations

import logging
from typing import Any

from django.dispatch import receiver

from micboard.services.manufacturer_service import (
    device_status_changed,
    sync_completed,
)

logger = logging.getLogger(__name__)


@receiver(device_status_changed)
def broadcast_device_status(
    sender: Any,
    *,
    service_code: str,
    device_id: int,
    device_type: str,
    status: str,
    is_active: bool,
    **kwargs: Any,
) -> None:
    """
    Broadcast device status changes via WebSocket.

    Args:
        sender: Service that emitted the signal
        service_code: Manufacturer service code
        device_id: Device primary key
        device_type: Type of device (Receiver/Transmitter)
        status: New status
        is_active: Active flag
        **kwargs: Additional signal kwargs
    """
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()
        if not channel_layer:
            return

        # Broadcast to micboard_updates group
        async_to_sync(channel_layer.group_send)(
            "micboard_updates",
            {
                "type": "device_status_update",
                "service_code": service_code,
                "device_id": device_id,
                "device_type": device_type,
                "status": status,
                "is_active": is_active,
            },
        )

        logger.debug(
            f"Broadcasted status change: {device_type} {device_id} -> {status}",
            extra={
                "service_code": service_code,
                "device_id": device_id,
                "device_type": device_type,
                "status": status,
            },
        )

    except Exception as e:
        logger.error(
            f"Failed to broadcast device status: {e}",
            exc_info=True,
            extra={
                "device_id": device_id,
                "device_type": device_type,
            },
        )


@receiver(sync_completed)
def broadcast_sync_completion(
    sender: Any,
    *,
    service_code: str,
    sync_result: dict,
    **kwargs: Any,
) -> None:
    """
    Broadcast sync completion via WebSocket.

    Args:
        sender: Service that emitted the signal
        service_code: Manufacturer service code
        sync_result: Sync result data
        **kwargs: Additional signal kwargs
    """
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()
        if not channel_layer:
            return

        # Broadcast to micboard_updates group
        async_to_sync(channel_layer.group_send)(
            "micboard_updates",
            {
                "type": "sync_completed",
                "service_code": service_code,
                "device_count": sync_result.get("device_count", 0),
                "online_count": sync_result.get("online_count", 0),
                "status": sync_result.get("status", "success"),
            },
        )

        logger.debug(
            f"Broadcasted sync completion: {service_code}",
            extra={
                "service_code": service_code,
                "sync_result": sync_result,
            },
        )

    except Exception as e:
        logger.error(
            f"Failed to broadcast sync completion: {e}",
            exc_info=True,
            extra={"service_code": service_code},
        )
