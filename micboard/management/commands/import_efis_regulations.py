"""Management command to import EFIS regulatory data.

Imports frequency band data from the ECO Frequency Information System (EFIS).
Can be run manually or scheduled via cron/tasks.
"""

import logging
import time

from django.core.management.base import BaseCommand

from micboard.services.efis_import import EFISImportService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Import EFIS regulatory data."""

    help = "Import regulatory frequency data from EFIS (Annex 1)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force import even if data is fresh (less than 30 days old)",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Enable verbose output with detailed progress information",
        )

    def handle(self, *args, **options):
        force = options["force"]
        verbose = options.get("verbose", False)

        start_time = time.time()

        self.stdout.write(self.style.HTTP_INFO("=" * 70))
        self.stdout.write(self.style.HTTP_INFO("EFIS Regulatory Data Import"))
        self.stdout.write(self.style.HTTP_INFO("=" * 70))
        self.stdout.write("")

        self.stdout.write("Checking EFIS data freshness...")

        if not force and not EFISImportService.is_outdated():
            last_date = EFISImportService.get_last_import_date()
            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS(f"✓ EFIS data is fresh (last import: {last_date})")
            )
            self.stdout.write(self.style.WARNING("  Use --force to override and re-import anyway."))
            return

        last_date = EFISImportService.get_last_import_date()
        if last_date:
            self.stdout.write(self.style.WARNING(f"  Last import: {last_date}"))
        else:
            self.stdout.write(self.style.WARNING("  No previous import found"))

        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("Starting import from EFIS API..."))
        self.stdout.write(f"  API endpoint: {EFISImportService.EFIS_URL}")
        self.stdout.write(f"  Timeout: {EFISImportService.REQUEST_TIMEOUT_SECONDS}s per request")
        self.stdout.write("")

        if verbose:
            self.stdout.write("Fetching regions and wireless audio application terms...")

        result = EFISImportService.run_import()

        elapsed_time = time.time() - start_time

        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("-" * 70))

        if result["success"]:
            self.stdout.write(self.style.SUCCESS(f"✓ {result['message']}"))
            self.stdout.write("")
            self.stdout.write(self.style.HTTP_INFO("Import Summary:"))
            self.stdout.write(f"  • Regulatory domains updated: {result.get('domains_updated', 0)}")
            self.stdout.write(f"  • Frequency bands created: {result.get('bands_created', 0)}")
            self.stdout.write(f"  • Frequency bands updated: {result.get('bands_updated', 0)}")
            self.stdout.write(f"  • Total processing time: {elapsed_time:.2f} seconds")
            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS(
                    "✓ Import completed successfully. Frequency bands are now up to date."
                )
            )
        else:
            self.stdout.write(self.style.ERROR(f"✗ Import failed: {result['message']}"))
            self.stdout.write("")
            self.stdout.write(
                self.style.ERROR("Please check the logs for detailed error information.")
            )

        self.stdout.write(self.style.HTTP_INFO("=" * 70))
