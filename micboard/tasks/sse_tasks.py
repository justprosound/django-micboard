"""
SSE subscription tasks for real-time updates.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import Manufacturer, Receiver
from micboard.tasks.polling_tasks import _update_models_from_api_data

logger = logging.getLogger(__name__)


def start_sse_subscriptions(manufacturer_id: int):
    """
    Start SSE subscriptions for all active devices of a manufacturer.
    This runs indefinitely until stopped.
    """
    try:
        manufacturer = Manufacturer.objects.get(pk=manufacturer_id)
        plugin_class = get_manufacturer_plugin(manufacturer.code)
        plugin = plugin_class(manufacturer)

        if not hasattr(plugin, 'connect_and_subscribe'):
            logger.error("Plugin %s does not support SSE subscriptions", manufacturer.code)
            return

        # Get active devices
        devices = list(
            Receiver.objects.filter(
                manufacturer=manufacturer,
                is_active=True
            ).values_list('api_device_id', flat=True)
        )

        if not devices:
            logger.info("No active devices found for SSE subscriptions on %s", manufacturer.name)
            return

        logger.info("Starting SSE subscriptions for %d devices on %s", len(devices), manufacturer.name)

        # Run the async subscriptions
        asyncio.run(_run_sse_subscriptions_async(plugin, devices))

    except Manufacturer.DoesNotExist:
        logger.error("Manufacturer with ID %s not found for SSE subscriptions", manufacturer_id)
    except Exception as e:
        logger.exception("Error in SSE subscriptions for manufacturer ID %s: %s", manufacturer_id, e)


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
    async def update_callback(data: dict[str, Any]):
        """Handle SSE update data."""
        logger.info("SSE update for %s: %s", device_id, data)
        await _process_sse_update_async(plugin, device_id, data)

    try:
        await plugin.connect_and_subscribe(device_id, update_callback)
    except Exception as e:
        logger.exception("Error subscribing to device %s: %s", device_id, e)


async def _process_sse_update_async(plugin, device_id: str, data: dict[str, Any]):
    """Process SSE update data asynchronously."""
    try:
        manufacturer = plugin.manufacturer

        # Transform and update
        transformed_data = plugin.transform_device_data(data)
        if transformed_data:
            api_data = [data]
            updated_count = _update_models_from_api_data(api_data, manufacturer, plugin)
            if updated_count > 0:
                logger.info("Updated %d device(s) from SSE for %s", updated_count, device_id)
        else:
            logger.debug("Could not transform SSE data for %s", device_id)

    except Exception as e:
        logger.exception("Error processing SSE update for %s: %s", device_id, e)
