"""Management command to add Shure devices for discovery via System API."""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

import httpx

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import DiscoveredDevice

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Add Shure device IP addresses for discovery"

    def add_arguments(self, parser):
        parser.add_argument(
            "--ips",
            type=str,
            required=True,
            help="Comma-separated list of device IP addresses (e.g., '172.21.1.100,172.21.1.101')",
        )
        parser.add_argument(
            "--manufacturer",
            type=str,
            default="shure",
            help="Manufacturer code (default: shure)",
        )

    def handle(self, *args, **options):
        manufacturer_code = options["manufacturer"]
        ips_str = options["ips"]

        try:
            manufacturer = Manufacturer.objects.get(code=manufacturer_code)
        except Manufacturer.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Manufacturer '{manufacturer_code}' not found"))
            return

        # Parse IP addresses
        ip_addresses = [ip.strip() for ip in ips_str.split(",") if ip.strip()]

        if not ip_addresses:
            self.stderr.write(self.style.ERROR("No valid IP addresses provided"))
            return

        self.stdout.write(f"Adding {len(ip_addresses)} devices for {manufacturer.name}...")
        added_count = 0
        failed_count = 0

        with httpx.Client(timeout=1) as client:
            for ip in ip_addresses:
                self.stdout.write(f"  Checking {ip}...", ending=" ")

                try:
                    # Probe common device endpoints before recording the candidate.
                    for protocol in ["http", "https"]:
                        for port in [80, 443]:
                            try:
                                client.get(f"{protocol}://{ip}:{port}")
                                break
                            except httpx.RequestError:
                                continue
                        else:
                            continue
                        break

                    # Create or update discovered device record
                    _device, created = DiscoveredDevice.objects.update_or_create(
                        ip=ip,
                        defaults={
                            "manufacturer": manufacturer,
                            "device_type": "shure_device",
                            "channels": 0,  # Will be updated by polling
                        },
                    )

                    if created:
                        self.stdout.write(self.style.SUCCESS("✓ Added"))
                    else:
                        self.stdout.write(self.style.WARNING("⟳ Updated"))

                    added_count += 1

                except Exception as e:
                    logger.exception("Failed to add discovered device at %s", ip)
                    self.stderr.write(self.style.ERROR(f"✗ Failed: {e}"))
                    failed_count += 1

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(f"Added/updated {added_count} devices, {failed_count} failed")
        )
        self.stdout.write("")
        self.stdout.write(
            "Now run: uv run --no-sync python manage.py poll_devices --manufacturer shure"
        )
