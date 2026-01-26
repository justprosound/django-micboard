"""SSE subscription tasks for real-time updates."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import Manufacturer, WirelessChassis
from micboard.tasks.polling_tasks import _update_models_from_api_data

logger = logging.getLogger(__name__)


def start_sse_subscriptions(manufacturer_id: int):
    """Start SSE subscriptions for all active devices of a manufacturer.
    This runs indefinitely until stopped.
    """
    try:
        manufacturer = Manufacturer.objects.get(pk=manufacturer_id)
        plugin_class = get_manufacturer_plugin(manufacturer.code)
        plugin = plugin_class(manufacturer)

        if not hasattr(plugin, "connect_and_subscribe"):
            logger.error("Plugin %s does not support SSE subscriptions", manufacturer.code)
            return

        # Get active devices
        devices = list(
            WirelessChassis.objects.filter(manufacturer=manufacturer, status="online").values_list(
                "api_device_id", flat=True
            )
        )

        if not devices:
            logger.info("No active devices found for SSE subscriptions on %s", manufacturer.name)
            return

        logger.info(
            "Starting SSE subscriptions for %d devices on %s", len(devices), manufacturer.name
        )

        # Run the async subscriptions
        asyncio.run(_run_sse_subscriptions_async(plugin, devices))

    except Manufacturer.DoesNotExist:
        logger.error("Manufacturer with ID %s not found for SSE subscriptions", manufacturer_id)
    except Exception as e:
        logger.exception(
            "Error in SSE subscriptions for manufacturer ID %s: %s", manufacturer_id, e
        )


async def _run_sse_subscriptions_async(plugin, device_ids: list[str]):
    """Run SSE subscriptions asynchronously."""
    tasks = []

    for device_id in device_ids:
        task = asyncio.create_task(_subscribe_device_async(plugin, device_id))
        tasks.append(task)

    # Wait for all tasks
    await asyncio.gather(*tasks, return_exceptions=True)


async def _subscribe_device_async(plugin, device_id: str):
    """Subscribe to a single device asynchronously."""
    try:
        logger.info("Starting SSE subscription for device: %s", device_id)

        # Get receiver for connection tracking
        from micboard.models import RealTimeConnection, WirelessChassis

        try:
            chassis = WirelessChassis.objects.get(
                manufacturer=plugin.manufacturer, api_device_id=device_id
            )
            connection, created = RealTimeConnection.objects.get_or_create(
                chassis=chassis, defaults={"connection_type": "sse"}
            )
            if not created:
                connection.connection_type = "sse"
                connection.save()
            connection.mark_connecting()
        except WirelessChassis.DoesNotExist:
            logger.warning("Receiver not found for SSE subscription: %s", device_id)
            connection = None

        async def update_callback(data: dict[str, Any]):
            """Handle SSE update data."""
            if connection:
                connection.received_message()
            logger.info("SSE update for %s: %s", device_id, data)
            await _process_sse_update_async(plugin, device_id, data)

        await plugin.connect_and_subscribe(device_id, update_callback)
    except Exception as e:
        logger.exception("Error subscribing to device %s: %s", device_id, e)
        if "connection" in locals() and connection:
            connection.mark_error(str(e))


async def _process_sse_update_async(plugin, device_id: str, data: dict[str, Any]):
    """Process SSE update data asynchronously."""
    try:
        manufacturer = plugin.manufacturer

        # Transform and update - SSE data should be similar to API data format
        # The plugin's transform_device_data expects the raw API format
        transformed_data = plugin.transform_device_data(data)
        if transformed_data:
            # Update the specific device using the transformed data
            api_device_id = transformed_data.get("api_device_id")
            if api_device_id:
                # Create a single-device API data list for the update function
                api_data = [data]  # Raw API data
                updated_count = _update_models_from_api_data(api_data, manufacturer, plugin)
                if updated_count > 0:
                    logger.info("Updated %d device(s) from SSE for %s", updated_count, device_id)

                    # Broadcast the update via WebSocket
                    await _broadcast_sse_update_async(manufacturer, transformed_data)
                else:
                    logger.debug("No updates from SSE data for %s", device_id)
            else:
                logger.warning("No api_device_id in transformed SSE data for %s", device_id)
        else:
            logger.debug("Could not transform SSE data for %s", device_id)

    except Exception as e:
        logger.exception("Error processing SSE update for %s: %s", device_id, e)


async def _broadcast_sse_update_async(manufacturer, device_data: dict[str, Any]):
    """Broadcast SSE update via WebSocket channels."""
    try:
        from channels.layers import get_channel_layer

        from micboard.serializers import serialize_receiver
        from micboard.signals.broadcast_signals import devices_polled

        # Get the updated receiver data
        api_device_id = device_data.get("api_device_id")
        if api_device_id:
            from micboard.models import WirelessChassis

            try:
                chassis = WirelessChassis.objects.get(
                    manufacturer=manufacturer, api_device_id=api_device_id
                )
                serialized_data = {"receivers": [serialize_receiver(chassis, include_extra=True)]}

                # Send via Django Channels
                channel_layer = get_channel_layer()
                if channel_layer:
                    await channel_layer.group_send(
                        "micboard_updates",
                        {
                            "type": "device_update",
                            "manufacturer": manufacturer.code,
                            "data": serialized_data,
                        },
                    )

                # Also emit the devices_polled signal for compatibility
                devices_polled.send(sender=None, manufacturer=manufacturer, data=serialized_data)

                logger.debug("Broadcasted SSE update for device %s", api_device_id)

            except WirelessChassis.DoesNotExist:
                logger.warning("Receiver not found for SSE broadcast: %s", api_device_id)

    except Exception as e:
        logger.exception("Error broadcasting SSE update: %s", e)
