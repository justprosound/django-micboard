"""Management command to import Shure devices from System API into Django models."""

import logging

from django.core.management.base import BaseCommand

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Import Shure devices from System API servers into Django models"

    def add_arguments(self, parser):
        parser.add_argument(
            "--server-id",
            type=str,
            help="Import from specific server ID (from MICBOARD_CONFIG.MANUFACTURER_API_SERVERS)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without making changes",
        )
        parser.add_argument(
            "--full",
            action="store_true",
            help="Show detailed device information",
        )

    def handle(self, *args, **options):
        from micboard.apps import MicboardConfig

        config = MicboardConfig.get_config()

        # Get API servers configuration
        api_servers = config.get("MANUFACTURER_API_SERVERS", {})

        # Fallback to single server config
        if not api_servers:
            base_url = config.get("SHURE_API_BASE_URL", "https://localhost:10000")
            shared_key = config.get("SHURE_API_SHARED_KEY")
            verify_ssl = config.get("SHURE_API_VERIFY_SSL", False)

            if not shared_key:
                self.stdout.write(
                    self.style.ERROR(
                        "No API servers configured. Set MICBOARD_CONFIG.MANUFACTURER_API_SERVERS or "
                        "MICBOARD_CONFIG.SHURE_API_SHARED_KEY in settings."
                    )
                )
                return

            api_servers = {
                "default": {
                    "manufacturer": "shure",
                    "base_url": base_url,
                    "shared_key": shared_key,
                    "verify_ssl": verify_ssl,
                    "location_id": None,
                }
            }

        # Filter by server ID if specified
        if options["server_id"]:
            if options["server_id"] not in api_servers:
                self.stdout.write(
                    self.style.ERROR(
                        f"Server ID '{options['server_id']}' not found in configuration"
                    )
                )
                return
            api_servers = {options["server_id"]: api_servers[options["server_id"]]}

        # Ensure Shure manufacturer exists
        manufacturer, _ = Manufacturer.objects.get_or_create(
            code="shure", defaults={"name": "Shure", "is_active": True}
        )

        self.stdout.write(
            self.style.SUCCESS(f"\nImporting from {len(api_servers)} API server(s)...\n")
        )

        total_discovered = 0
        total_imported = 0
        total_updated = 0

        from micboard.services.import_service import ImportService

        service = ImportService()
        total_discovered, total_imported, total_updated = service.import_from_servers(
            api_servers=api_servers, manufacturer=manufacturer, options=options
        )

        # Summary from service
        self.stdout.write(f"\n{'=' * 70}")
        self.stdout.write(self.style.SUCCESS("IMPORT SUMMARY"))
        self.stdout.write(f"{'=' * 70}")
        self.stdout.write(f"Total discovered: {total_discovered}")
        self.stdout.write(f"Newly imported: {total_imported}")
        self.stdout.write(f"Updated: {total_updated}")
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\n(DRY RUN - No changes made)"))

        # Summary
        self.stdout.write(f"\n{'=' * 70}")
        self.stdout.write(self.style.SUCCESS("IMPORT SUMMARY"))
        self.stdout.write(f"{'=' * 70}")
        self.stdout.write(f"Total discovered: {total_discovered}")
        self.stdout.write(f"Newly imported: {total_imported}")
        self.stdout.write(f"Updated: {total_updated}")
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\n(DRY RUN - No changes made)"))

    def _import_device(self, device, manufacturer, location, server_id, dry_run=False, full=False):
        """Delegate import logic to ImportService for testability and reuse."""
        from micboard.services.import_service import ImportService

        service = ImportService()
        created, updated = service.import_device(
            device=device,
            manufacturer=manufacturer,
            location=location,
            server_id=server_id,
            dry_run=dry_run,
            full=full,
        )

        # Preserve previous command behaviour around printing when full/dry_run
        if full:
            serial = device.get("serial") or device.get("serialNumber")
            if not serial:
                self.stdout.write(
                    self.style.WARNING(f"  Skipping device without serial number: {device}")
                )
            else:
                if dry_run:
                    exists = WirelessChassis.objects.filter(serial_number=serial).exists()
                    if exists:
                        self.stdout.write(f"    Would update: {serial}")
                    else:
                        self.stdout.write(f"    Would create: {serial}")
                else:
                    if created:
                        self.stdout.write(self.style.SUCCESS(f"    ✓ Created: {serial}"))
                    elif updated:
                        self.stdout.write(f"    ✓ Updated: {serial}")

        return created, updated
