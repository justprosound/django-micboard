"""Start the bounded SSE subscription supervisor from the command line."""

from __future__ import annotations

import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.realtime.sse_subscription_service import run_sse_subscriptions
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Thin foreground adapter for the SSE subscription service."""

    help = "Start bounded SSE subscriptions for one manufacturer"

    def add_arguments(self, parser: CommandParser) -> None:
        """Register manufacturer and optional single-device selectors."""
        parser.add_argument(
            "--manufacturer",
            type=str,
            default="sennheiser",
            help="Manufacturer code to subscribe to (default: sennheiser)",
        )
        parser.add_argument(
            "--device",
            type=str,
            help="Optional API device ID to subscribe to",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Resolve the manufacturer and run the shared singleton supervisor."""
        manufacturer_code = str(options.get("manufacturer") or "sennheiser")
        device_id = options.get("device")
        try:
            manufacturer = Manufacturer.objects.get(code=manufacturer_code)
        except Manufacturer.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Manufacturer '{manufacturer_code}' not found"))
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
            run_sse_subscriptions(manufacturer.pk, chassis_id=chassis_id)
        except KeyboardInterrupt:
            self.stdout.write("SSE subscriptions stopped by user")
        except Exception as exc:
            logger.exception(
                "SSE subscription command failed for manufacturer %s",
                manufacturer.pk,
                exc_info=sanitized_exception_info(exc),
            )
            self.stderr.write(self.style.ERROR("SSE subscription failed; details redacted"))
