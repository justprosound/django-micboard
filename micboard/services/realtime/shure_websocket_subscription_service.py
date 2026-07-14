"""Bounded Shure WebSocket subscription orchestration for realtime updates."""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any

from asgiref.sync import sync_to_async

from micboard.integrations.shure.websocket import connect_and_subscribe
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
    build_device_https_url,
)
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


def run_shure_websocket_subscriptions(
    manufacturer_id: int,
    *,
    chassis_id: int | None = None,
) -> None:
    """Run the singleton, bounded WebSocket supervisor for one Shure manufacturer."""
    try:
        try:
            manufacturer = Manufacturer.objects.get(
                pk=manufacturer_id,
                code="shure",
                is_active=True,
            )
        except Manufacturer.DoesNotExist:
            logger.warning(
                "Realtime manufacturer ID %s was not found, inactive, or does not support "
                "WebSockets",
                manufacturer_id,
            )
            return

        plugin_class = get_manufacturer_plugin(manufacturer.code)
        plugin = plugin_class(manufacturer)

        limits = RealtimeSubscriptionSupervisor.limits()
        lease = RealtimeSubscriptionSupervisor.acquire(
            transport="websocket",
            scope=manufacturer_id,
        )
        if lease is None:
            logger.info(
                "WebSocket subscription supervisor is already active for manufacturer ID %s",
                manufacturer.pk,
            )
            return

        active_chassis = RealtimeSubscriptionLifecycleService.select_chassis(
            manufacturer_id=manufacturer_id,
            chassis_id=chassis_id,
            transport="websocket",
            limit=limits.max_devices,
        )
        if not active_chassis:
            logger.info("No active wireless chassis found")
            return

        async def reload_chassis() -> list[WirelessChassis]:
            manufacturer_active = await sync_to_async(
                ManufacturerActivationService.is_active,
                thread_sensitive=True,
            )(manufacturer_id)
            if not manufacturer_active:
                return []
            return await sync_to_async(
                RealtimeSubscriptionLifecycleService.select_chassis,
                thread_sensitive=True,
            )(
                manufacturer_id=manufacturer_id,
                chassis_id=chassis_id,
                transport="websocket",
                limit=limits.max_devices,
            )

        asyncio.run(
            RealtimeSubscriptionSupervisor.run(
                items=active_chassis,
                subscribe=partial(_start_receiver_websocket_async, plugin),
                lease=lease,
                limits=limits,
                reload_items=reload_chassis,
            )
        )

    except Exception as exc:
        logger.exception(
            "Error starting WebSocket subscriptions for manufacturer ID %s",
            manufacturer_id,
            exc_info=sanitized_exception_info(exc),
        )


def _get_or_create_websocket_connection(chassis: Any) -> Any:
    """Create connection tracking in Django's synchronous database context."""
    from micboard.models.realtime.connection import RealTimeConnection

    connection, created = RealTimeConnection.objects.get_or_create(
        chassis=chassis,
        defaults={"connection_type": "websocket"},
    )
    if not created:
        connection.connection_type = "websocket"
        connection.save(update_fields=["connection_type", "updated_at"])
    mark_connecting(connection)
    return connection


async def _start_receiver_websocket_async(plugin: Any, chassis: Any) -> None:
    """Start WebSocket subscription for a single receiver."""
    client = None
    connection = None
    try:
        logger.info(
            "Starting WebSocket subscription for chassis ID %s",
            getattr(chassis, "pk", None),
        )

        connection = await sync_to_async(
            _get_or_create_websocket_connection,
            thread_sensitive=True,
        )(chassis)

        from micboard.integrations.shure.client import ShureSystemAPIClient

        base_url = build_device_https_url(
            ip_address=chassis.ip,
            port=getattr(chassis, "port", 443),
        )

        client = await sync_to_async(
            ShureSystemAPIClient,
            thread_sensitive=True,
        )(base_url=base_url)

        async def update_callback(data: dict[str, Any]) -> None:
            await sync_to_async(received_message, thread_sensitive=True)(connection)
            await RealtimeSubscriptionLifecycleService.process_update(
                plugin=plugin,
                data=data,
                transport="websocket",
            )

        manufacturer_id = getattr(getattr(plugin, "manufacturer", None), "pk", None)
        if not isinstance(manufacturer_id, int):
            logger.error(
                "WebSocket subscription stopped because manufacturer identity is unavailable"
            )
            await sync_to_async(mark_stopped, thread_sensitive=True)(connection)
            return
        manufacturer_active = await sync_to_async(
            ManufacturerActivationService.is_active,
            thread_sensitive=True,
        )(manufacturer_id)
        if not manufacturer_active:
            logger.info(
                "WebSocket subscription stopped for inactive manufacturer ID %s",
                manufacturer_id,
            )
            await sync_to_async(mark_stopped, thread_sensitive=True)(connection)
            return
        await connect_and_subscribe(client, chassis.api_device_id, update_callback)

    except Exception as exc:
        logger.exception(
            "Error in WebSocket subscription for chassis ID %s",
            getattr(chassis, "pk", None),
            exc_info=sanitized_exception_info(exc),
        )
        if connection is not None:
            error_status = f"WebSocket subscription failed: {type(exc).__name__}"[:160]
            await sync_to_async(mark_error, thread_sensitive=True)(connection, error_status)
    finally:
        if client is not None:
            try:
                await sync_to_async(client.close, thread_sensitive=True)()
            except Exception as exc:
                logger.exception(
                    "Failed to close WebSocket API client for chassis ID %s",
                    getattr(chassis, "pk", None),
                    exc_info=sanitized_exception_info(exc),
                )
