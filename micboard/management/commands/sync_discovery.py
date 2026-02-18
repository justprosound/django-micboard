"""Management command to synchronize discovery between Django and manufacturer APIs.

This command pushes DiscoveredDevice IPs from Django to manufacturer APIs (like Shure System API)
and then pulls device data back to Django. Django Micboard is the "source of truth" for device IPs.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from micboard.models import Manufacturer
from micboard.tasks.sync.discovery import run_discovery_sync_task


class Command(BaseCommand):
    help = (
        "Synchronize discovery IPs between Django and manufacturer APIs (Django is source of truth)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--manufacturer",
            type=str,
            help="Manufacturer code (e.g., 'shure', 'sennheiser'). If not specified, syncs all.",
        )
        parser.add_argument(
            "--scan-cidrs",
            action="store_true",
            help="Expand CIDRs and add all IPs to discovery",
        )
        parser.add_argument(
            "--scan-fqdns",
            action="store_true",
            help="Resolve FQDNs and add all IPs to discovery",
        )
        parser.add_argument(
            "--max-hosts",
            type=int,
            default=1024,
            help="Maximum number of hosts to scan per CIDR (default: 1024)",
        )

    def handle(self, *args, **options):
        manufacturer_code = options.get("manufacturer")
        scan_cidrs = options.get("scan_cidrs", False)
        scan_fqdns = options.get("scan_fqdns", False)
        max_hosts = options.get("max_hosts", 1024)

        if manufacturer_code:
            try:
                manufacturer = Manufacturer.objects.get(code=manufacturer_code)
                manufacturers = [manufacturer]
            except Manufacturer.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Manufacturer with code '{manufacturer_code}' not found")
                )
                return
        else:
            manufacturers = Manufacturer.objects.filter(is_active=True)

        if not manufacturers:
            self.stdout.write(self.style.WARNING("No active manufacturers found"))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Starting discovery sync for {len(manufacturers)} manufacturer(s)..."
            )
        )
        self.stdout.write(f"  Scan CIDRs: {scan_cidrs}")
        self.stdout.write(f"  Scan FQDNs: {scan_fqdns}")
        self.stdout.write(f"  Max hosts per CIDR: {max_hosts}")
        self.stdout.write("")

        for manufacturer in manufacturers:
            self.stdout.write(f"Processing {manufacturer.name} ({manufacturer.code})...")

            # Run the discovery sync task
            result = run_discovery_sync_task(
                manufacturer_id=manufacturer.id,
                add_cidrs=None,
                add_fqdns=None,
                scan_cidrs=scan_cidrs,
                scan_fqdns=scan_fqdns,
                max_hosts=max_hosts,
            )

            # Display results
            status = result.get("status", "unknown")
            if status == "success":
                self.stdout.write(self.style.SUCCESS("  ✓ Sync completed successfully"))
            elif status == "failed":
                self.stdout.write(self.style.ERROR("  ✗ Sync failed"))
            else:
                self.stdout.write(self.style.WARNING(f"  Status: {status}"))

            self.stdout.write(f"  Created receivers: {result.get('created_receivers', 0)}")
            self.stdout.write(f"  Missing IPs submitted: {result.get('missing_ips_submitted', 0)}")
            self.stdout.write(f"  Scanned IPs submitted: {result.get('scanned_ips_submitted', 0)}")

            if result.get("errors"):
                self.stdout.write(self.style.WARNING("  Errors:"))
                for error in result["errors"]:
                    self.stdout.write(self.style.WARNING(f"    - {error}"))

            self.stdout.write("")

        self.stdout.write(self.style.SUCCESS("Discovery sync completed for all manufacturers"))
