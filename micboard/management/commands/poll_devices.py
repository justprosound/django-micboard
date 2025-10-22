"""
Management command to poll device APIs and update models.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

from micboard.models import Manufacturer
from micboard.tasks.polling_tasks import poll_manufacturer_devices

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Poll manufacturer APIs for device data and update models"

    def add_arguments(self, parser):
        parser.add_argument(
            "--manufacturer",
            type=str,
            help="Code of specific manufacturer to poll (e.g., 'shure'). If not provided, polls all manufacturers.",
        )
        parser.add_argument(
            "--async",
            action="store_true",
            help="Run polling asynchronously using Django-Q",
        )

    def handle(self, *args, **options):
        manufacturer_code = options.get("manufacturer")
        use_async = options.get("async", False)

        if manufacturer_code:
            try:
                manufacturer = Manufacturer.objects.get(code=manufacturer_code)
                manufacturers = [manufacturer]
            except Manufacturer.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Manufacturer '{manufacturer_code}' not found"))
                return
        else:
            manufacturers = Manufacturer.objects.filter(is_active=True)
            if not manufacturers:
                self.stdout.write("No active manufacturers found")
                return

        self.stdout.write(f"Starting device polling for {len(manufacturers)} manufacturer(s)...")

        for manufacturer in manufacturers:
            self.stdout.write(f"Polling {manufacturer.name} ({manufacturer.code})...")

            if use_async:
                # Import here to avoid issues if Django-Q not installed
                from django_q.tasks import async_task

                async_task(poll_manufacturer_devices, manufacturer.id)
                self.stdout.write(
                    self.style.SUCCESS(f"Enqueued async polling task for {manufacturer.name}")
                )
            else:
                try:
                    poll_manufacturer_devices(manufacturer.id)
                    self.stdout.write(
                        self.style.SUCCESS(f"Successfully polled {manufacturer.name}")
                    )
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"Error polling {manufacturer.name}: {e}"))
                    logger.exception("Error in poll_devices command")

        self.stdout.write("Device polling completed.")
