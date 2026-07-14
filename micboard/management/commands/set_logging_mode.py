"""Management command to set audit logging verbosity mode."""

from django.core.management.base import BaseCommand

from micboard.services.maintenance.logging_mode import LoggingModeService


class Command(BaseCommand):
    help = "Set audit logging verbosity mode (passive/normal/high)"

    def add_arguments(self, parser):
        parser.add_argument(
            "mode",
            type=str,
            choices=["passive", "normal", "high"],
            help="Logging verbosity mode",
        )
        parser.add_argument(
            "--duration",
            type=int,
            default=None,
            help="Duration in minutes (for high mode only; auto-downgrades to normal after expiry)",
        )

    def handle(self, *args, **options):
        mode = options["mode"]
        duration = options.get("duration")

        ttl_seconds = duration * 60 if duration is not None else None
        LoggingModeService.set_mode(mode, ttl_seconds=ttl_seconds)

        self.stdout.write(self.style.SUCCESS(f"Logging mode set to: {mode}"))
        if duration is not None:
            self.stdout.write(f"  Duration: {duration} minute(s)")
