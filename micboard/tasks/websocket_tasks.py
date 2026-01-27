"""WebSocket background tasks for real-time device updates.

This module handles WebSocket connections for manufacturers that support
real-time updates via WebSocket (currently Shure).
"""

import asyncio
import logging
from typing import Any

from micboard.utils.dependencies import HAS_DJANGO_Q

if HAS_DJANGO_Q:
    from django_q.tasks import async_task
else:
    def async_task(func):
        return func

from micboard.integrations.shure.websocket import connect_and_subscribe
from micboard.manufacturers import get_manufacturer_plugin
from micboard.tasks.polling_tasks import _update_models_from_api_data

logger = logging.getLogger(__name__)


@async_task
def start_shure_websocket_subscriptions():
    """Start WebSocket subscriptions for all active Shure devices.

    This task runs in the background and maintains WebSocket connections
    to Shure devices for real-time updates.
    """
    try:
        from micboard.models import Manufacturer

        # Get Shure manufacturer
        try:
            manufacturer = Manufacturer.objects.get(code="shure")
        except Manufacturer.DoesNotExist:
            logger.warning("Shure manufacturer not found, skipping WebSocket subscriptions")
            return

        # Get Shure plugin
        plugin = get_manufacturer_plugin(manufacturer.code)
        if not plugin:
            logger.error("Shure plugin not found")
            return

        # Get active chassis
        active_chassis = manufacturer.wireless_chassis.filter(status="online")
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


async def _start_receiver_websocket_async(plugin, chassis):
    """Start WebSocket subscription for a single receiver."""
    try:
        logger.info("Starting WebSocket subscription for Shure receiver: %s", chassis.name)

        # Get or create connection tracking
        from micboard.models import RealTimeConnection

        connection, created = RealTimeConnection.objects.get_or_create(
            chassis=chassis, defaults={"connection_type": "websocket"}
        )
        if not created:
            connection.connection_type = "websocket"
            connection.save()

        connection.mark_connecting()

        # Create API client for the WebSocket connection
        from micboard.integrations.shure.client import ShureSystemAPIClient

        # Construct base_url
        scheme = (
            "https" if getattr(chassis, "port", 443) == 443 else "http"
        )  # Assuming 443 is HTTPS, otherwise HTTP
        base_url = f"{scheme}://{chassis.ip}:{getattr(chassis, 'port', 443)}"

        client = ShureSystemAPIClient(
            base_url=base_url, verify_ssl=getattr(chassis, "verify_ssl", True)
        )

        # Set up callback for updates
        from asgiref.sync import async_to_sync  # Add this import

        def update_callback(data: dict[str, Any]):
            connection.received_message()
            async_to_sync(_process_websocket_update_async)(plugin, chassis.api_device_id, data)

        # Connect and subscribe using the WebSocket function
        await connect_and_subscribe(client, chassis.api_device_id, update_callback)

    except Exception as e:
        logger.exception("Error in WebSocket subscription for chassis %s: %s", chassis.name, e)
        if "connection" in locals():
            connection.mark_error(str(e))


async def _process_websocket_update_async(plugin, device_id: str, data: dict[str, Any]):
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
                updated_count = _update_models_from_api_data(api_data, manufacturer, plugin)
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

    except Exception as e:
        logger.exception("Error processing WebSocket update for %s: %s", device_id, e)


async def _broadcast_websocket_update_async(manufacturer, device_data: dict[str, Any]):
    """Broadcast WebSocket update via BroadcastService."""
    try:
        from micboard.serializers import serialize_receiver
        from micboard.services.broadcast_service import BroadcastService

        # Get the updated chassis data
        api_device_id = device_data.get("api_device_id")
        if api_device_id:
            from micboard.models import WirelessChassis

            try:
                chassis = WirelessChassis.objects.get(
                    manufacturer=manufacturer, api_device_id=api_device_id
                )
                serialized_data = {"receivers": [serialize_receiver(chassis, include_extra=True)]}

                # Broadcast update
                BroadcastService.broadcast_device_update(
                    manufacturer=manufacturer, data=serialized_data
                )

                logger.debug("Broadcasted WebSocket update for device %s", api_device_id)

            except WirelessChassis.DoesNotExist:
                logger.warning(
                    "Wireless chassis not found for WebSocket broadcast: %s", api_device_id
                )

    except Exception as e:
        logger.exception("Error broadcasting WebSocket update: %s", e)
