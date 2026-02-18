"""Broadcast service for real-time UI updates.

Replaces Django signals for WebSocket broadcasting to provide more explicit
control and easier debugging.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # For type checking only - Channels may not be installed in all environments
    from channels.layers import BaseChannelLayer  # pragma: no cover

from asgiref.sync import async_to_sync

try:
    from channels.layers import get_channel_layer
except ImportError:

    def get_channel_layer(alias: str = "") -> BaseChannelLayer | None:
        """Fallback stub when Channels is not installed."""
        return None


logger = logging.getLogger(__name__)


class BroadcastService:
    """Handles broadcasting updates to WebSocket clients."""

    @staticmethod
    def broadcast_device_update(*, manufacturer: Any, data: Any) -> None:
        """Broadcast polled device data to WebSocket clients."""
        try:
            channel_layer = get_channel_layer()
            if not channel_layer:
                logger.debug("No channel layer configured; skipping broadcast")
                return

            async_to_sync(channel_layer.group_send)(
                "micboard_updates", {"type": "device_update", "data": data}
            )
            logger.debug(
                "Broadcasted device update for manufacturer %s",
                getattr(manufacturer, "code", str(manufacturer)),
            )
        except Exception:
            logger.exception("Failed to broadcast device update")

    @staticmethod
    def broadcast_api_health(*, manufacturer: Any, health_data: dict[str, Any]) -> None:
        """Broadcast API health status to WebSocket clients."""
        try:
            channel_layer = get_channel_layer()
            if not channel_layer:
                logger.debug("No channel layer configured; skipping API health broadcast")
                return

            async_to_sync(channel_layer.group_send)(
                "micboard_updates",
                {
                    "type": "api_health_update",
                    "manufacturer_code": getattr(manufacturer, "code", None),
                    "health_data": health_data,
                },
            )
            logger.debug(
                "Broadcasted API health update for manufacturer %s",
                getattr(manufacturer, "code", str(manufacturer)),
            )
        except Exception:
            logger.exception("Failed to broadcast API health update")

    @staticmethod
    def broadcast_device_status(
        *,
        service_code: str,
        device_id: int,
        device_type: str,
        status: str,
        is_active: bool,
    ) -> None:
        """Broadcast device status changes via WebSocket."""
        try:
            channel_layer = get_channel_layer()
            if not channel_layer:
                return

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
            logger.debug(f"Broadcasted status change: {device_type} {device_id} -> {status}")
        except Exception:
            logger.exception("Failed to broadcast device status update")

    @staticmethod
    def broadcast_sync_completion(
        *,
        service_code: str,
        sync_result: dict[str, Any],
    ) -> None:
        """Broadcast sync completion via WebSocket."""
        try:
            channel_layer = get_channel_layer()
            if not channel_layer:
                return

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
            logger.debug(f"Broadcasted sync completion: {service_code}")
        except Exception:
            logger.exception("Failed to broadcast sync completion update")

    @staticmethod
    def broadcast_discovery_approved(
        *,
        queue_item_id: int,
        manufacturer_code: str,
        device_count: int,
    ) -> None:
        """Broadcast discovery approval via WebSocket."""
        try:
            channel_layer = get_channel_layer()
            if not channel_layer:
                return

            async_to_sync(channel_layer.group_send)(
                "micboard_updates",
                {
                    "type": "discovery_approved",
                    "queue_item_id": queue_item_id,
                    "manufacturer_code": manufacturer_code,
                    "device_count": device_count,
                },
            )
            logger.debug(f"Broadcasted discovery approval for {manufacturer_code}")
        except Exception:
            logger.exception("Failed to broadcast discovery approval")

    @staticmethod
    def broadcast_error(
        *,
        error_type: str,
        error_message: str,
        manufacturer_code: str | None = None,
        device_id: int | None = None,
    ) -> None:
        """Broadcast error notification via WebSocket."""
        try:
            from django.utils import timezone

            channel_layer = get_channel_layer()
            if not channel_layer:
                return

            async_to_sync(channel_layer.group_send)(
                "micboard_updates",
                {
                    "type": "error_notification",
                    "error_type": error_type,
                    "message": error_message,
                    "manufacturer_code": manufacturer_code,
                    "device_id": device_id,
                    "timestamp": timezone.now().isoformat(),
                },
            )
            logger.debug(f"Broadcasted error: {error_type}")
        except Exception:
            logger.exception("Failed to broadcast error notification")
