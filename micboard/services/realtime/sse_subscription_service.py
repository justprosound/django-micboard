"""Bounded SSE subscription orchestration for realtime device updates."""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any

from asgiref.sync import sync_to_async

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.common.base.plugin import get_manufacturer_plugin
from micboard.services.manufacturer.activation_service import ManufacturerActivationService
from micboard.services.realtime.connection_service import (
    mark_connecting,
    mark_error,
    mark_stopped,
    received_message,
)
from micboard.services.realtime.subscription_lifecycle_service import (
    RealtimeSubscriptionLifecycleService,
)
from micboard.services.realtime.subscription_supervisor import (
    RealtimeSubscriptionSupervisor,
)
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

        selected_chassis = RealtimeSubscriptionLifecycleService.select_chassis(
            manufacturer_id=manufacturer_id,
            chassis_id=chassis_id,
            transport="sse",
            limit=limits.max_devices,
        )
        devices = [chassis.api_device_id for chassis in selected_chassis]
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
            selected = await sync_to_async(
                RealtimeSubscriptionLifecycleService.select_chassis,
                thread_sensitive=True,
            )(
                manufacturer_id=manufacturer_id,
                chassis_id=chassis_id,
                transport="sse",
                limit=limits.max_devices,
            )
            return [chassis.api_device_id for chassis in selected]

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


def _get_or_create_sse_connection(plugin: Any, device_id: str) -> Any:
    """Create connection tracking in Django's synchronous database context."""
    from micboard.models.realtime.connection import RealTimeConnection

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
        await RealtimeSubscriptionLifecycleService.process_update(
            plugin=plugin,
            data=data,
            transport="sse",
        )

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
