"""Bounded SSE subscription orchestration for realtime device updates."""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any

from asgiref.sync import sync_to_async

from micboard.models.discovery import Manufacturer
from micboard.models.hardware import WirelessChassis
from micboard.services.common.base.plugin import get_manufacturer_plugin
from micboard.services.manufacturer.activation_service import ManufacturerActivationService
from micboard.services.realtime.connection_service import (
    mark_connecting,
    mark_error,
    mark_stopped,
    received_message,
)
from micboard.services.realtime.subscription_supervisor import (
    RealtimeSubscriptionSupervisor,
)
from micboard.services.sync.device_update_service import DeviceUpdateService
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


def run_sse_subscriptions(manufacturer_id: int, *, chassis_id: int | None = None) -> None:
    """Run the singleton, bounded SSE supervisor for one manufacturer."""
    try:
        manufacturer = Manufacturer.objects.get(pk=manufacturer_id, is_active=True)
        plugin_class = get_manufacturer_plugin(manufacturer.code)
        plugin = plugin_class(manufacturer)

        if not hasattr(plugin, "connect_and_subscribe"):
            logger.error(
                "Plugin for manufacturer ID %s does not support SSE subscriptions",
                manufacturer.pk,
            )
            return

        limits = RealtimeSubscriptionSupervisor.limits()
        lease = RealtimeSubscriptionSupervisor.acquire(
            transport="sse",
            scope=manufacturer_id,
        )
        if lease is None:
            logger.info(
                "SSE subscription supervisor is already active for manufacturer ID %s",
                manufacturer_id,
            )
            return

        devices = _select_sse_subscription_devices(
            manufacturer_id=manufacturer_id,
            chassis_id=chassis_id,
            limit=limits.max_devices,
        )
        if not devices:
            logger.info(
                "No active devices found for SSE subscriptions on manufacturer ID %s",
                manufacturer.pk,
            )
            return

        async def reload_devices() -> list[str]:
            manufacturer_active = await sync_to_async(
                ManufacturerActivationService.is_active,
                thread_sensitive=True,
            )(manufacturer_id)
            if not manufacturer_active:
                return []
            return await sync_to_async(
                _select_sse_subscription_devices,
                thread_sensitive=True,
            )(
                manufacturer_id=manufacturer_id,
                chassis_id=chassis_id,
                limit=limits.max_devices,
            )

        logger.info(
            "Starting SSE subscriptions for %d devices on manufacturer ID %s",
            len(devices),
            manufacturer.pk,
        )

        asyncio.run(
            RealtimeSubscriptionSupervisor.run(
                items=devices,
                subscribe=partial(_subscribe_device_async, plugin),
                lease=lease,
                limits=limits,
                reload_items=reload_devices,
            )
        )

    except Manufacturer.DoesNotExist:
        logger.error(
            "Manufacturer with ID %s not found or inactive for SSE subscriptions",
            manufacturer_id,
        )
    except Exception as exc:
        logger.exception(
            "Error in SSE subscriptions for manufacturer ID %s",
            manufacturer_id,
            exc_info=sanitized_exception_info(exc),
        )


def _select_sse_subscription_devices(
    *,
    manufacturer_id: int,
    chassis_id: int | None,
    limit: int,
) -> list[str]:
    """Load one bounded fair device window in synchronous ORM context."""
    devices_query = WirelessChassis.objects.filter(
        manufacturer_id=manufacturer_id,
        manufacturer__is_active=True,
        status__in=("online", "degraded", "provisioning"),
    )
    if chassis_id is not None:
        devices_query = devices_query.filter(pk=chassis_id)
        selected_chassis = list(devices_query.order_by("pk")[:limit])
    else:
        selected_chassis = RealtimeSubscriptionSupervisor.select_fair_queryset_batch(
            queryset=devices_query,
            transport="sse",
            scope=manufacturer_id,
            limit=limit,
        )
    return [chassis.api_device_id for chassis in selected_chassis]


def _get_or_create_sse_connection(plugin: Any, device_id: str) -> Any:
    """Create connection tracking in Django's synchronous database context."""
    from micboard.models.realtime import RealTimeConnection

    chassis = WirelessChassis.objects.get(
        manufacturer=plugin.manufacturer,
        api_device_id=device_id,
    )
    connection, created = RealTimeConnection.objects.get_or_create(
        chassis=chassis,
        defaults={"connection_type": "sse"},
    )
    if not created:
        connection.connection_type = "sse"
        connection.save(update_fields=["connection_type", "updated_at"])
    mark_connecting(connection)
    return connection


async def _subscribe_device_async(plugin: Any, device_id: str) -> None:
    """Subscribe to a single device asynchronously."""
    manufacturer_id = getattr(getattr(plugin, "manufacturer", None), "pk", None)
    logger.info("Starting SSE device subscription for manufacturer ID %s", manufacturer_id)
    if not isinstance(manufacturer_id, int):
        logger.error("SSE subscription stopped because manufacturer identity is unavailable")
        return

    connection = None
    try:
        connection = await sync_to_async(
            _get_or_create_sse_connection,
            thread_sensitive=True,
        )(
            plugin,
            device_id,
        )
    except WirelessChassis.DoesNotExist:
        logger.warning(
            "Receiver not found for SSE subscription on manufacturer ID %s",
            manufacturer_id,
        )
        connection = None

    async def update_callback(data: dict[str, Any]) -> None:
        """Handle SSE update data."""
        if connection:
            await sync_to_async(received_message, thread_sensitive=True)(connection)
        logger.debug("Received SSE update for manufacturer ID %s", manufacturer_id)
        await _process_sse_update_async(plugin, data)

    try:
        manufacturer_active = await sync_to_async(
            ManufacturerActivationService.is_active,
            thread_sensitive=True,
        )(manufacturer_id)
        if not manufacturer_active:
            logger.info(
                "SSE subscription stopped for inactive manufacturer ID %s",
                manufacturer_id,
            )
            if connection:
                await sync_to_async(mark_stopped, thread_sensitive=True)(connection)
            return
        await plugin.connect_and_subscribe(device_id, update_callback)
    except Exception as exc:
        logger.exception(
            "Error subscribing to SSE device for manufacturer ID %s",
            manufacturer_id,
            exc_info=sanitized_exception_info(exc),
        )
        if connection:
            error_status = f"SSE subscription failed: {type(exc).__name__}"[:160]
            await sync_to_async(mark_error, thread_sensitive=True)(connection, error_status)


async def _process_sse_update_async(
    plugin: Any,
    data: dict[str, Any],
) -> None:
    """Process SSE update data asynchronously."""
    try:
        manufacturer = plugin.manufacturer

        transformed_data = plugin.transform_device_data(data)
        if transformed_data:
            api_device_id = transformed_data.get("api_device_id")
            if api_device_id:
                updated_count = await sync_to_async(
                    DeviceUpdateService.update_models_from_api_data,
                    thread_sensitive=True,
                )(
                    api_data=[data],
                    manufacturer=manufacturer,
                    plugin=plugin,
                )
                if updated_count > 0:
                    logger.info(
                        "Updated %d device(s) from SSE for manufacturer ID %s",
                        updated_count,
                        getattr(manufacturer, "pk", None),
                    )
                    await _broadcast_sse_update_async(manufacturer, transformed_data)
                else:
                    logger.debug(
                        "No persisted updates from SSE for manufacturer ID %s",
                        getattr(manufacturer, "pk", None),
                    )
            else:
                logger.warning(
                    "Transformed SSE update omitted its device identifier for manufacturer ID %s",
                    getattr(manufacturer, "pk", None),
                )
        else:
            logger.debug(
                "Could not transform SSE data for manufacturer ID %s",
                getattr(manufacturer, "pk", None),
            )

    except Exception as exc:
        logger.exception(
            "Error processing SSE update for manufacturer ID %s",
            getattr(plugin.manufacturer, "pk", None),
            exc_info=sanitized_exception_info(exc),
        )


def _broadcast_sse_update(manufacturer: Any, api_device_id: str) -> None:
    """Resolve and broadcast one device entirely in synchronous context."""
    from micboard.services.notification.broadcast_service import BroadcastService

    chassis = WirelessChassis.objects.get(
        manufacturer=manufacturer,
        api_device_id=api_device_id,
    )
    serialized_data = {
        "receivers": [
            {
                "id": chassis.id,
                "api_device_id": chassis.api_device_id,
                "name": chassis.name,
                "ip": str(chassis.ip) if chassis.ip else None,
                "status": chassis.status,
                "model": chassis.model,
            }
        ]
    }
    BroadcastService.broadcast_device_update(
        manufacturer=manufacturer,
        data=serialized_data,
    )


async def _broadcast_sse_update_async(
    manufacturer: Any,
    device_data: dict[str, Any],
) -> None:
    """Broadcast an SSE update without running synchronous services on the event loop."""
    api_device_id = device_data.get("api_device_id")
    if not api_device_id:
        return

    try:
        await sync_to_async(_broadcast_sse_update, thread_sensitive=True)(
            manufacturer,
            api_device_id,
        )
        logger.debug(
            "Broadcasted SSE update for manufacturer ID %s",
            getattr(manufacturer, "pk", None),
        )
    except WirelessChassis.DoesNotExist:
        logger.warning(
            "Receiver not found for SSE broadcast on manufacturer ID %s",
            getattr(manufacturer, "pk", None),
        )
    except Exception as exc:
        logger.exception(
            "Error broadcasting SSE update",
            exc_info=sanitized_exception_info(exc),
        )
