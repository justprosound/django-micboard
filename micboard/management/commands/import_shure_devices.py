"""Management command to import Shure devices from System API into Django models."""

import logging

from django.core.management.base import BaseCommand
from django.db import transaction

from micboard.integrations.shure.client import ShureSystemAPIClient
from micboard.models import Location, Manufacturer, WirelessChassis

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

        for server_id, server_config in api_servers.items():
            self.stdout.write(f"\n{'=' * 70}")
            self.stdout.write(f"Server: {server_id}")
            self.stdout.write(f"URL: {server_config['base_url']}")
            if server_config.get("location_id"):
                try:
                    location = Location.objects.get(id=server_config["location_id"])
                    self.stdout.write(f"Location: {location}")
                except Location.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(f"Location ID {server_config['location_id']} not found")
                    )
            self.stdout.write(f"{'=' * 70}\n")

            try:
                # Initialize client
                client = ShureSystemAPIClient(
                    base_url=server_config["base_url"],
                    verify_ssl=server_config.get("verify_ssl", False),
                )

                # Get devices
                devices = client.devices.get_devices()
                total_discovered += len(devices)

                self.stdout.write(f"Discovered {len(devices)} device(s) from {server_id}")

                # Get location if specified
                location = None
                if server_config.get("location_id"):
                    try:
                        location = Location.objects.get(id=server_config["location_id"])
                    except Location.DoesNotExist:
                        pass

                # Import each device
                for device in devices:
                    try:
                        imported, updated = self._import_device(
                            device=device,
                            manufacturer=manufacturer,
                            location=location,
                            server_id=server_id,
                            dry_run=options["dry_run"],
                            full=options["full"],
                        )
                        if imported:
                            total_imported += 1
                        if updated:
                            total_updated += 1
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f"Error importing device {device.get('serial', 'UNKNOWN')}: {e}"
                            )
                        )
                        if options["full"]:
                            import traceback

                            traceback.print_exc()

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to connect to {server_id}: {e}"))
                continue

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
        """Import or update a single device."""
        serial = device.get("serial") or device.get("serialNumber")
        model = device.get("model") or device.get("deviceType")
        ip = device.get("ip") or device.get("ipAddress")
        mac = device.get("mac") or device.get("macAddress")
        device_type = device.get("type", "UNKNOWN")

        if not serial:
            if full:
                self.stdout.write(
                    self.style.WARNING(f"  Skipping device without serial number: {device}")
                )
            return False, False

        if full:
            self.stdout.write(f"\n  Device: {model} - {serial}")
            self.stdout.write(f"    IP: {ip}")
            self.stdout.write(f"    Type: {device_type}")
            self.stdout.write(f"    State: {device.get('state', 'UNKNOWN')}")

        if dry_run:
            # Check if exists
            exists = WirelessChassis.objects.filter(serial_number=serial).exists()
            if exists:
                self.stdout.write(f"    Would update: {serial}")
                return False, True
            else:
                self.stdout.write(f"    Would create: {serial}")
                return True, False

        # Determine role based on device type
        role = "receiver"  # Default
        if "transmitter" in device_type.lower():
            role = "transmitter"
        elif "transceiver" in device_type.lower():
            role = "transceiver"

        # Import or update
        with transaction.atomic():
            chassis, created = WirelessChassis.objects.update_or_create(
                serial_number=serial,
                defaults={
                    "manufacturer": manufacturer,
                    "model": model or "Unknown",
                    "role": role,
                    "ip": ip,
                    "mac_address": mac,
                    "location": location,
                    "status": device.get("state", "unknown").lower(),
                    "is_online": device.get("state") == "ONLINE",
                    "api_device_id": device.get("id") or device.get("deviceId"),
                },
            )

            if created:
                if full:
                    self.stdout.write(self.style.SUCCESS(f"    ✓ Created: {serial}"))
                return True, False
            else:
                if full:
                    self.stdout.write(f"    ✓ Updated: {serial}")
                return False, True
