"""WebSocket background tasks for real-time device updates.

This module handles WebSocket connections for manufacturers that support
real-time updates via WebSocket (currently Shure).
"""

import asyncio
import logging
from typing import Any

from asgiref.sync import sync_to_async

from micboard.integrations.shure.websocket import connect_and_subscribe
from micboard.services.common.base.plugin import get_manufacturer_plugin
from micboard.tasks.sync.polling import _update_models_from_api_data

logger = logging.getLogger(__name__)


def start_shure_websocket_subscriptions() -> None:
    """Start WebSocket subscriptions for all active Shure devices.

    This task runs in the background and maintains WebSocket connections
    to Shure devices for real-time updates.
    """
    try:
        from micboard.models.discovery.manufacturer import Manufacturer
        from micboard.models.hardware.wireless_chassis import WirelessChassis

        # Get Shure manufacturer
        try:
            manufacturer = Manufacturer.objects.get(code="shure")
        except Manufacturer.DoesNotExist:
            logger.warning("Shure manufacturer not found, skipping WebSocket subscriptions")
            return

        # Get Shure plugin
        plugin_class = get_manufacturer_plugin(manufacturer.code)
        plugin = plugin_class(manufacturer)

        # Get active chassis
        active_chassis = WirelessChassis.objects.filter(
            manufacturer=manufacturer,
            status="online",
        )
        if not active_chassis:
            logger.info("No active wireless chassis found")
            return

        # Start WebSocket subscriptions for each chassis
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            tasks = []
            for chassis in active_chassis:
                task = loop.create_task(_start_receiver_websocket_async(plugin, chassis))
                tasks.append(task)

            if tasks:
                loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                logger.info("Started WebSocket subscriptions for %d Shure receivers", len(tasks))
            else:
                logger.info("No WebSocket subscriptions to start")

        finally:
            loop.close()

    except Exception as e:
        logger.exception("Error starting Shure WebSocket subscriptions: %s", e)


def _get_or_create_websocket_connection(chassis: Any) -> Any:
    """Create connection tracking in Django's synchronous database context."""
    from micboard.models.realtime import RealTimeConnection

    connection, created = RealTimeConnection.objects.get_or_create(
        chassis=chassis,
        defaults={"connection_type": "websocket"},
    )
    if not created:
        connection.connection_type = "websocket"
        connection.save(update_fields=["connection_type", "updated_at"])
    connection.mark_connecting()
    return connection


async def _start_receiver_websocket_async(plugin: Any, chassis: Any) -> None:
    """Start WebSocket subscription for a single receiver."""
    client = None
    connection = None
    try:
        logger.info("Starting WebSocket subscription for Shure receiver: %s", chassis.name)

        connection = await sync_to_async(
            _get_or_create_websocket_connection,
            thread_sensitive=True,
        )(chassis)

        # Create API client for the WebSocket connection
        from micboard.integrations.shure.client import ShureSystemAPIClient

        # Manufacturer credentials must only cross authenticated TLS.
        base_url = f"https://{chassis.ip}:{getattr(chassis, 'port', 443)}"

        client = await sync_to_async(
            ShureSystemAPIClient,
            thread_sensitive=True,
        )(base_url=base_url)

        # Set up callback for updates
        async def update_callback(data: dict[str, Any]) -> None:
            await sync_to_async(connection.received_message, thread_sensitive=True)()
            await _process_websocket_update_async(plugin, chassis.api_device_id, data)

        # Connect and subscribe using the WebSocket function
        await connect_and_subscribe(client, chassis.api_device_id, update_callback)

    except Exception as exc:
        logger.exception("Error in WebSocket subscription for chassis %s", chassis.name)
        if connection is not None:
            error_status = f"WebSocket subscription failed: {type(exc).__name__}"[:160]
            await sync_to_async(connection.mark_error, thread_sensitive=True)(error_status)
    finally:
        if client is not None:
            try:
                await sync_to_async(client.close, thread_sensitive=True)()
            except Exception:
                logger.exception(
                    "Failed to close WebSocket API client for chassis %s", chassis.name
                )


async def _process_websocket_update_async(
    plugin: Any,
    device_id: str,
    data: dict[str, Any],
) -> None:
    """Process WebSocket update data asynchronously."""
    try:
        manufacturer = plugin.manufacturer

        # Transform and update - WebSocket data should be similar to API data format
        # The plugin's transform_device_data expects the raw API format
        transformed_data = plugin.transform_device_data(data)
        if transformed_data:
            # Update the specific device using the transformed data
            api_device_id = transformed_data.get("api_device_id")
            if api_device_id:
                # Create a single-device API data list for the update function
                api_data = [data]  # Raw API data
                updated_count = await sync_to_async(
                    _update_models_from_api_data,
                    thread_sensitive=True,
                )(api_data, manufacturer, plugin)
                if updated_count > 0:
                    logger.info(
                        "Updated %d device(s) from WebSocket for %s", updated_count, device_id
                    )

                    # Broadcast the update via WebSocket
                    await _broadcast_websocket_update_async(manufacturer, transformed_data)
                else:
                    logger.debug("No updates from WebSocket data for %s", device_id)
            else:
                logger.warning("No api_device_id in transformed WebSocket data for %s", device_id)
        else:
            logger.debug("Could not transform WebSocket data for %s", device_id)

    except Exception:
        logger.exception("Error processing WebSocket update for %s", device_id)


def _broadcast_websocket_update(manufacturer: Any, api_device_id: str) -> None:
    """Resolve and broadcast one device entirely in synchronous context."""
    from micboard.models.hardware import WirelessChassis
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


async def _broadcast_websocket_update_async(
    manufacturer: Any,
    device_data: dict[str, Any],
) -> None:
    """Broadcast a WebSocket update without synchronous work on the event loop."""
    from micboard.models.hardware import WirelessChassis

    api_device_id = device_data.get("api_device_id")
    if not api_device_id:
        return

    try:
        await sync_to_async(_broadcast_websocket_update, thread_sensitive=True)(
            manufacturer,
            api_device_id,
        )
        logger.debug("Broadcasted WebSocket update for device %s", api_device_id)
    except WirelessChassis.DoesNotExist:
        logger.warning("Wireless chassis not found for WebSocket broadcast: %s", api_device_id)
    except Exception:
        logger.exception("Error broadcasting WebSocket update")
