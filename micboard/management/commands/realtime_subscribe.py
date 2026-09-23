"""Start the bounded realtime subscription supervisor from the command line."""

from __future__ import annotations

import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.realtime.subscription_runner import run_realtime_subscriptions
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Thin foreground adapter for the realtime subscription runner."""

    help = "Start bounded realtime subscriptions for one manufacturer"

    def add_arguments(self, parser: CommandParser) -> None:
        """Register the manufacturer and optional single-device selectors."""
        parser.add_argument(
            "--manufacturer",
            type=str,
            required=True,
            help="Manufacturer code to subscribe to",
        )
        parser.add_argument(
            "--device",
            type=str,
            help="Optional API device ID to subscribe to",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Resolve the manufacturer and run the singleton supervisor for its transport."""
        manufacturer_code = str(options.get("manufacturer") or "")
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
            run_realtime_subscriptions(manufacturer.pk, chassis_id=chassis_id)
        except KeyboardInterrupt:
            self.stdout.write("Realtime subscriptions stopped by user")
        except Exception as exc:
            logger.exception(
                "Realtime subscription command failed for manufacturer %s",
                manufacturer.pk,
                exc_info=sanitized_exception_info(exc),
            )
            self.stderr.write(self.style.ERROR("Realtime subscription failed; details redacted"))
