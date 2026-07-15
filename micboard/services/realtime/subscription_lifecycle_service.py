"""Shared lifecycle for realtime subscription inventory and device updates."""

from __future__ import annotations

import logging
from typing import Any, Literal

from asgiref.sync import sync_to_async

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.notification.broadcast_service import BroadcastService
from micboard.services.realtime.subscription_supervisor import (
    RealtimeSubscriptionSupervisor,
)
from micboard.services.sync.device_update_service import DeviceUpdateService
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

RealtimeTransport = Literal["sse", "websocket"]
_TRANSPORT_LABELS: dict[RealtimeTransport, str] = {
    "sse": "SSE",
    "websocket": "WebSocket",
}


class RealtimeSubscriptionLifecycleService:
    """Select subscription inventory and persist transport-neutral device events."""

    @classmethod
    def select_chassis(
        cls,
        *,
        manufacturer_id: int,
        chassis_id: int | None,
        transport: RealtimeTransport,
        limit: int,
    ) -> list[WirelessChassis]:
        """Load one bounded active chassis window for either realtime transport."""
        queryset = WirelessChassis.objects.filter(
            manufacturer_id=manufacturer_id,
            manufacturer__is_active=True,
            status__in=("online", "degraded", "provisioning"),
        )
        if chassis_id is not None:
            return list(queryset.filter(pk=chassis_id).order_by("pk")[:limit])
        return RealtimeSubscriptionSupervisor.select_fair_queryset_batch(
            queryset=queryset,
            transport=transport,
            scope=manufacturer_id,
            limit=limit,
        )

    @classmethod
    async def process_update(
        cls,
        *,
        plugin: Any,
        data: dict[str, Any],
        transport: RealtimeTransport,
    ) -> None:
        """Transform, persist, and broadcast one transport-neutral realtime update."""
        manufacturer: Any = getattr(plugin, "manufacturer", None)
        manufacturer_id = getattr(manufacturer, "pk", None)
        transport_label = _TRANSPORT_LABELS[transport]
        try:
            transformed_data = plugin.transform_device_data(data)
            if not transformed_data:
                logger.debug(
                    "Could not transform %s data for manufacturer ID %s",
                    transport_label,
                    manufacturer_id,
                )
                return

            api_device_id = transformed_data.get("api_device_id")
            if not api_device_id:
                logger.warning(
                    "Transformed %s update omitted its device identifier for manufacturer ID %s",
                    transport_label,
                    manufacturer_id,
                )
                return

            updated_count = await sync_to_async(
                DeviceUpdateService.update_models_from_api_data,
                thread_sensitive=True,
            )(
                api_data=[data],
                manufacturer=manufacturer,
                plugin=plugin,
            )
            if updated_count <= 0:
                logger.debug(
                    "No persisted updates from %s for manufacturer ID %s",
                    transport_label,
                    manufacturer_id,
                )
                return

            logger.info(
                "Updated %d device(s) from %s for manufacturer ID %s",
                updated_count,
                transport_label,
                manufacturer_id,
            )
            await cls._broadcast_update_async(
                manufacturer=manufacturer,
                api_device_id=api_device_id,
                transport=transport,
            )
        except Exception as exc:
            logger.exception(
                "Error processing %s update for manufacturer ID %s",
                transport_label,
                manufacturer_id,
                exc_info=sanitized_exception_info(exc),
            )

    @classmethod
    async def _broadcast_update_async(
        cls,
        *,
        manufacturer: Any,
        api_device_id: str,
        transport: RealtimeTransport,
    ) -> None:
        """Resolve and broadcast one persisted chassis outside the event-loop thread."""
        transport_label = _TRANSPORT_LABELS[transport]
        manufacturer_id = getattr(manufacturer, "pk", None)
        try:
            await sync_to_async(cls._broadcast_update, thread_sensitive=True)(
                manufacturer=manufacturer,
                api_device_id=api_device_id,
            )
            logger.debug(
                "Broadcasted %s update for manufacturer ID %s",
                transport_label,
                manufacturer_id,
            )
        except WirelessChassis.DoesNotExist:
            logger.warning(
                "Wireless chassis not found for %s broadcast on manufacturer ID %s",
                transport_label,
                manufacturer_id,
            )
        except Exception as exc:
            logger.exception(
                "Error broadcasting %s update for manufacturer ID %s",
                transport_label,
                manufacturer_id,
                exc_info=sanitized_exception_info(exc),
            )

    @staticmethod
    def _broadcast_update(*, manufacturer: Any, api_device_id: str) -> None:
        """Project one persisted chassis and send the canonical device payload."""
        chassis = WirelessChassis.objects.get(
            manufacturer=manufacturer,
            api_device_id=api_device_id,
        )
        BroadcastService.broadcast_device_update(
            manufacturer=manufacturer,
            data={"receivers": [RealtimeSubscriptionLifecycleService._project_chassis(chassis)]},
        )

    @staticmethod
    def _project_chassis(chassis: WirelessChassis) -> dict[str, Any]:
        """Return the stable primitive receiver projection used by realtime broadcasts."""
        return {
            "id": chassis.id,
            "api_device_id": chassis.api_device_id,
            "name": chassis.name,
            "ip": str(chassis.ip) if chassis.ip else None,
            "status": chassis.status,
            "model": chassis.model,
        }
