"""Management command to poll device APIs using the service layer."""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError

from micboard.models import Manufacturer
from micboard.services import PollingService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Poll manufacturer APIs for device data and update models.

    Uses the centralized PollingService to coordinate between manufacturer
    plugins, model updates, and real-time broadcasts.
    """

    help = "Poll manufacturer APIs for device data and update models"

    # Skip Django system checks to allow running in minimal/demo setups
    requires_system_checks: tuple[str, ...] = ()
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument(
            "--manufacturer",
            type=str,
            help=(
                "Code of specific manufacturer to poll (e.g., 'shure'). "
                "If not provided, polls all active."
            ),
        )
        parser.add_argument(
            "--async",
            action="store_true",
            help="Run polling asynchronously using Django-Q",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force polling even if manufacturer is marked inactive",
        )

    def handle(self, *args, **options):
        manufacturer_code = options.get("manufacturer")
        use_async = options.get("async", False)
        options.get("force", False)

        try:
            if manufacturer_code:
                try:
                    manufacturer = Manufacturer.objects.get(code=manufacturer_code)
                    manufacturers = [manufacturer]
                except Manufacturer.DoesNotExist:
                    raise CommandError(f"Manufacturer '{manufacturer_code}' not found") from None
            else:
                manufacturers = Manufacturer.objects.filter(is_active=True)
                if not manufacturers.exists():
                    self.stdout.write(
                        self.style.WARNING("No active manufacturers found for polling")
                    )
                    return

            self.stdout.write(
                self.style.HTTP_INFO(
                    f"Starting device polling for {len(manufacturers)} manufacturer(s)..."
                )
            )

            # Initialize PollingService
            polling_service = PollingService()

            for manufacturer in manufacturers:
                self.stdout.write(f"Polling {manufacturer.name} ({manufacturer.code})...")

                if use_async:
                    from micboard.utils.dependencies import HAS_DJANGO_Q
                    if HAS_DJANGO_Q:
                        try:
                            # PollingService handle async internally or via task wrapper
                            from django_q.tasks import async_task

                            from micboard.tasks.polling_tasks import poll_manufacturer_devices

                            async_task(poll_manufacturer_devices, manufacturer.id)
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"Enqueued async polling task for {manufacturer.name}"
                                )
                            )
                        except Exception as e:
                            self.stderr.write(
                                self.style.ERROR(f"Failed to enqueue async task: {e}")
                            )
                    else:
                        self.stderr.write(
                            self.style.ERROR("Django-Q not installed. Cannot run async.")
                        )
                else:
                    try:
                        # Synchronous polling via service
                        result = polling_service.poll_manufacturer(manufacturer)

                        summary = (
                            f"Success: {result.get('devices_created', 0)} created, "
                            f"{result.get('devices_updated', 0)} updated, "
                            f"{result.get('transmitters_synced', 0)} transmitters"
                        )
                        self.stdout.write(self.style.SUCCESS(f"[{manufacturer.code}] {summary}"))

                    except Exception as e:
                        logger.exception("Error polling %s", manufacturer.code)
                        self.stderr.write(
                            self.style.ERROR(f"Error polling {manufacturer.name}: {str(e)}")
                        )

            self.stdout.write(self.style.SUCCESS("Device polling command completed."))

        except CommandError as e:
            self.stderr.write(self.style.ERROR(str(e)))
        except Exception as e:
            logger.exception("Unexpected error in poll_devices command")
            self.stderr.write(self.style.ERROR(f"An unexpected error occurred: {str(e)}"))
