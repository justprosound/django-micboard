"""Management command to poll device APIs using the service layer."""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.services.sync.polling_service import PollingService

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
                "Code of specific manufacturer to poll (e.g., 'shure'). If not provided, polls all active."
            ),
        )
        parser.add_argument(
            "--async",
            action="store_true",
            help="Run polling asynchronously using the configured native Huey queue",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force polling even if manufacturer is marked inactive",
        )

    def handle(self, *args, **options):
        manufacturer_code = options.get("manufacturer")
        use_async = options.get("async", False)
        force = options.get("force", False)

        try:
            manufacturers = self._get_manufacturers(manufacturer_code, force=force)
            if not manufacturers:
                self.stdout.write(self.style.WARNING("No manufacturers found for polling"))
                return

            self.stdout.write(
                self.style.HTTP_INFO(
                    f"Starting device polling for {len(manufacturers)} manufacturer(s)..."
                )
            )
            polling_service = PollingService()
            for manufacturer in manufacturers:
                if use_async:
                    self._enqueue_manufacturer(manufacturer)
                else:
                    self._poll_manufacturer(polling_service, manufacturer)

            self.stdout.write(self.style.SUCCESS("Device polling command completed."))
        except CommandError as e:
            self.stderr.write(self.style.ERROR(str(e)))
        except Exception as e:
            logger.exception("Unexpected error in poll_devices command")
            self.stderr.write(self.style.ERROR(f"An unexpected error occurred: {e!s}"))

    @staticmethod
    def _get_manufacturers(manufacturer_code: str | None, *, force: bool):
        if manufacturer_code:
            try:
                return [Manufacturer.objects.get(code=manufacturer_code)]
            except Manufacturer.DoesNotExist:
                raise CommandError(f"Manufacturer '{manufacturer_code}' not found") from None

        queryset = (
            Manufacturer.objects.all() if force else Manufacturer.objects.filter(is_active=True)
        )
        return list(queryset)

    def _enqueue_manufacturer(self, manufacturer) -> None:
        from micboard.utils.dependencies import enqueue_huey_task, huey_is_configured

        if not huey_is_configured():
            self.stderr.write(
                self.style.ERROR("Native Huey is unavailable or unconfigured. Cannot run async.")
            )
            return

        try:
            from micboard.tasks.sync.polling import poll_manufacturer_devices

            enqueue_huey_task(poll_manufacturer_devices, manufacturer.pk)
            self.stdout.write(
                self.style.SUCCESS(f"Enqueued async polling task for {manufacturer.name}")
            )
        except Exception as exc:
            logger.exception("Failed to enqueue polling for %s", manufacturer.code)
            self.stderr.write(self.style.ERROR(f"Failed to enqueue async task: {exc}"))

    def _poll_manufacturer(self, polling_service: PollingService, manufacturer) -> None:
        self.stdout.write(f"Polling {manufacturer.name} ({manufacturer.code})...")
        try:
            result = polling_service.poll_manufacturer(manufacturer)
            summary = (
                f"Success: {result.get('devices_created', 0)} created, "
                f"{result.get('devices_updated', 0)} updated, "
                f"{result.get('units_synced', 0)} wireless units"
            )
            self.stdout.write(self.style.SUCCESS(f"[{manufacturer.code}] {summary}"))
        except Exception as exc:
            logger.exception("Error polling %s", manufacturer.code)
            self.stderr.write(self.style.ERROR(f"Error polling {manufacturer.name}: {exc!s}"))
