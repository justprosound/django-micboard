"""Start the bounded Shure WebSocket supervisor from the command line."""

from __future__ import annotations

import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.realtime.shure_websocket_subscription_service import (
    run_shure_websocket_subscriptions,
)
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Thin foreground adapter for the Shure WebSocket subscription service."""

    help = "Start bounded WebSocket subscriptions for Shure devices"

    def add_arguments(self, parser: CommandParser) -> None:
        """Register the supported manufacturer and optional device selector."""
        parser.add_argument(
            "--manufacturer",
            type=str,
            default="shure",
            help="Manufacturer code to subscribe to (default: shure)",
        )
        parser.add_argument(
            "--device",
            type=str,
            help="Optional API device ID to subscribe to",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Validate Shure availability and run the shared singleton supervisor."""
        manufacturer_code = str(options.get("manufacturer") or "shure")
        device_id = options.get("device")
        try:
            manufacturer = Manufacturer.objects.get(code=manufacturer_code)
        except Manufacturer.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Manufacturer '{manufacturer_code}' not found"))
            return

        if manufacturer.code != "shure":
            self.stderr.write(
                self.style.ERROR("WebSocket subscriptions are only supported for Shure")
            )
            return

        chassis_id = None
        if device_id:
            try:
                chassis_id = WirelessChassis.objects.get(
                    manufacturer=manufacturer,
                    api_device_id=device_id,
                ).pk
            except WirelessChassis.DoesNotExist:
                self.stderr.write(self.style.ERROR("Selected device was not found"))
                return

        try:
            run_shure_websocket_subscriptions(manufacturer.pk, chassis_id=chassis_id)
        except KeyboardInterrupt:
            self.stdout.write("WebSocket subscriptions stopped by user")
        except Exception as exc:
            logger.exception(
                "WebSocket subscription command failed for manufacturer %s",
                manufacturer.pk,
                exc_info=sanitized_exception_info(exc),
            )
            self.stderr.write(self.style.ERROR("WebSocket subscription failed; details redacted"))
