"""Management command to poll device APIs using the service layer."""

from __future__ import annotations

import logging
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.services.manufacturer.sync import ManufacturerSyncService
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Poll manufacturer APIs for device data and update models.

    Uses the manufacturer inventory sync to coordinate between manufacturer
    plugins, model updates, and real-time broadcasts.
    """

    help = "Poll manufacturer APIs for device data and update models"

    # Skip Django system checks to allow running in minimal/demo setups
    requires_system_checks: tuple[str, ...] = ()
    requires_migrations_checks = False

    def add_arguments(self, parser: Any) -> Any:
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

    def handle(self, *args: Any, **options: Any) -> None:
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
            for manufacturer in manufacturers:
                if use_async:
                    self._enqueue_manufacturer(manufacturer, force=force)
                else:
                    self._poll_manufacturer(manufacturer, force=force)

            self.stdout.write(self.style.SUCCESS("Device polling command completed."))
        except CommandError as e:
            self.stderr.write(self.style.ERROR(str(e)))
        except Exception as exc:
            logger.exception(
                "Unexpected error in poll_devices command",
                exc_info=sanitized_exception_info(exc),
            )
            self.stderr.write(
                self.style.ERROR(
                    f"An unexpected error occurred ({type(exc).__name__}); details redacted."
                )
            )

    @staticmethod
    def _get_manufacturers(manufacturer_code: str | None, *, force: bool) -> Any:
        if manufacturer_code:
            try:
                filters: dict[str, str | bool] = {"code": manufacturer_code}
                if not force:
                    filters["is_active"] = True
                return [Manufacturer.objects.get(**filters)]
            except Manufacturer.DoesNotExist:
                raise CommandError(
                    f"Manufacturer '{manufacturer_code}' not found or inactive"
                ) from None

        queryset = (
            Manufacturer.objects.all() if force else Manufacturer.objects.filter(is_active=True)
        )
        return list(queryset)

    def _enqueue_manufacturer(self, manufacturer: Any, *, force: bool = False) -> None:
        """Queue one manufacturer poll while preserving an explicit force override."""
        from micboard.utils.dependencies import enqueue_huey_task, huey_is_configured

        if not huey_is_configured():
            self.stderr.write(
                self.style.ERROR("Native Huey is unavailable or unconfigured. Cannot run async.")
            )
            return

        try:
            from micboard.tasks.sync.polling import poll_manufacturer_devices

            enqueue_huey_task(poll_manufacturer_devices, manufacturer.pk, force=force)
            self.stdout.write(
                self.style.SUCCESS(f"Enqueued async polling task for {manufacturer.name}")
            )
        except Exception as exc:
            logger.exception(
                "Failed to enqueue polling for %s",
                manufacturer.code,
                exc_info=sanitized_exception_info(exc),
            )
            self.stderr.write(
                self.style.ERROR(
                    f"Failed to enqueue async task ({type(exc).__name__}); details redacted."
                )
            )

    def _poll_manufacturer(
        self,
        manufacturer: Any,
        *,
        force: bool = False,
    ) -> None:
        self.stdout.write(f"Polling {manufacturer.name} ({manufacturer.code})...")
        try:
            result = ManufacturerSyncService.sync_devices_for_manufacturer(
                manufacturer_code=manufacturer.code,
                force=force,
            )
            if not result.success:
                # Expected failures — a missing integration, an inventory over its limit, a
                # manufacturer deactivated mid-poll — are reported in the result rather than
                # raised, so they have to be read here or the poll looks like it worked.
                logger.warning(
                    "Poll reported %d failure(s) for %s",
                    len(result.errors),
                    manufacturer.code,
                    extra={"code": manufacturer.code, "errors": result.errors},
                )
                self.stderr.write(
                    self.style.ERROR(
                        f"[{manufacturer.code}] Poll failed with "
                        f"{len(result.errors)} error(s); details in the log."
                    )
                )
                return
            summary = (
                f"Success: {result.devices_added} created, "
                f"{result.devices_updated} updated, "
                f"{result.devices_examined} examined"
            )
            self.stdout.write(self.style.SUCCESS(f"[{manufacturer.code}] {summary}"))
        except Exception as exc:
            logger.exception(
                "Error polling %s",
                manufacturer.code,
                exc_info=sanitized_exception_info(exc),
            )
            self.stderr.write(
                self.style.ERROR(
                    f"Error polling {manufacturer.name} ({type(exc).__name__}); details redacted."
                )
            )
