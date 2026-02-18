"""Management command to start SSE subscriptions for Sennheiser devices."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Any

from django.core.management.base import BaseCommand

from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import Manufacturer, WirelessChassis
from micboard.tasks.sync.polling import _update_models_from_api_data

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Start SSE subscriptions for Sennheiser devices"

    def add_arguments(self, parser):
        parser.add_argument(
            "--manufacturer",
            type=str,
            default="sennheiser",
            help="Manufacturer code to subscribe to (default: sennheiser)",
        )
        parser.add_argument(
            "--device",
            type=str,
            help=(
                "Specific device ID to subscribe to. "
                "If not provided, subscribes to all active devices."
            ),
        )

    def handle(self, *args, **options):
        manufacturer_code = options.get("manufacturer")
        device_id = options.get("device")

        try:
            manufacturer = Manufacturer.objects.get(code=manufacturer_code)
        except Manufacturer.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Manufacturer '{manufacturer_code}' not found"))
            return

        plugin_class = get_manufacturer_plugin(manufacturer.code)
        plugin = plugin_class(manufacturer)

        if not hasattr(plugin, "connect_and_subscribe"):
            self.stderr.write(
                self.style.ERROR(f"Plugin {manufacturer_code} does not support SSE subscriptions")
            )
            return

        # Get devices to subscribe to
        if device_id:
            devices = [device_id]
        else:
            devices = list(
                WirelessChassis.objects.filter(
                    manufacturer=manufacturer, is_active=True
                ).values_list("api_device_id", flat=True)
            )

        if not devices:
            self.stdout.write("No active devices found to subscribe to")
            return

        self.stdout.write(f"Starting SSE subscriptions for {len(devices)} device(s)...")

        # Set up signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            self.stdout.write("\nShutting down SSE subscriptions...")
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Start subscriptions
        try:
            asyncio.run(self._run_subscriptions(plugin, devices))
        except KeyboardInterrupt:
            self.stdout.write("SSE subscriptions stopped by user")
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Error in SSE subscriptions: {e}"))
            logger.exception("SSE subscription error")

    async def _run_subscriptions(self, plugin, device_ids: list[str]):
        """Run SSE subscriptions for multiple devices concurrently."""
        tasks = []

        for device_id in device_ids:
            task = asyncio.create_task(self._subscribe_device(plugin, device_id))
            tasks.append(task)

        # Wait for all tasks (they run indefinitely until cancelled)
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _subscribe_device(self, plugin, device_id: str):
        """Subscribe to a single device and handle updates."""

        async def update_callback(data: dict[str, Any]):
            """Handle incoming SSE data."""
            self.stdout.write(f"Received update for {device_id}: {data}")
            # Process the update data and update models
            await self._process_sse_update(plugin, device_id, data)

        try:
            await plugin.connect_and_subscribe(device_id, update_callback)
        except Exception as e:
            logger.exception(f"Error subscribing to device {device_id}: {e}")
            self.stderr.write(self.style.ERROR(f"Failed to subscribe to {device_id}: {e}"))

    async def _process_sse_update(self, plugin, device_id: str, data: dict[str, Any]):
        """Process SSE update data and update models."""
        try:
            # The SSE data should contain updated device information
            # For now, assume it's similar to the full device data from REST API
            # In practice, it might be partial updates, but let's treat it as full updates

            # Get the manufacturer from the plugin
            manufacturer = plugin.manufacturer

            # Transform the data using the plugin
            transformed_data = plugin.transform_device_data(data)
            if transformed_data:
                # Update the specific device
                api_data = [data]  # Wrap in list for the update function
                updated_count = _update_models_from_api_data(api_data, manufacturer, plugin)
                if updated_count > 0:
                    self.stdout.write(f"Updated {updated_count} device(s) from SSE for {device_id}")
                else:
                    logger.debug("No updates from SSE data for %s", device_id)
            else:
                logger.debug("Could not transform SSE data for %s", device_id)

        except Exception as e:
            logger.exception(f"Error processing SSE update for {device_id}: {e}")
            self.stderr.write(self.style.ERROR(f"Error processing SSE update for {device_id}: {e}"))
