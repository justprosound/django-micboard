"""Service to import devices into WirelessChassis models.

This encapsulates the device import/update logic previously embedded in the
management command to make it reusable and easier to test.
"""

from __future__ import annotations

import logging

from django.db import transaction

from micboard.models.hardware.wireless_chassis import WirelessChassis

logger = logging.getLogger(__name__)


class ImportService:
    """Service responsible for importing a single device payload into the DB."""

    def import_device(
        self,
        device: dict,
        manufacturer,
        location=None,
        server_id: str | None = None,
        dry_run: bool = False,
        full: bool = False,
    ) -> tuple[bool, bool]:
        """Import or update a single device.

        Returns a tuple (created: bool, updated: bool).
        """
        serial = device.get("serial") or device.get("serialNumber")
        model = device.get("model") or device.get("deviceType")
        ip = device.get("ip") or device.get("ipAddress")
        mac = device.get("mac") or device.get("macAddress")
        api_device_id = device.get("id") or device.get("deviceId")
        device_type = device.get("type", "UNKNOWN")

        if not serial or not ip or api_device_id is None:
            return False, False

        if dry_run:
            exists = WirelessChassis.objects.filter(serial_number=serial).exists()
            # created, updated
            return (not exists, exists)

        # Determine role based on device type
        role = "receiver"
        dt_low = device_type.lower() if isinstance(device_type, str) else ""
        if "transmitter" in dt_low:
            role = "transmitter"
        elif "transceiver" in dt_low:
            role = "transceiver"

        with transaction.atomic():
            _chassis, created = WirelessChassis.objects.update_or_create(
                serial_number=str(serial),
                defaults={
                    "manufacturer": manufacturer,
                    "model": model or "Unknown",
                    "role": role,
                    "ip": str(ip),
                    "mac_address": mac,
                    "location": location,
                    "status": (device.get("state") or "unknown").lower(),
                    "is_online": device.get("state") == "ONLINE",
                    "api_device_id": str(api_device_id),
                },
            )

            if created:
                return True, False
            return False, True

    def import_from_servers(
        self, api_servers: dict, manufacturer, options: dict
    ) -> tuple[int, int, int]:
        """Import devices from multiple API servers.

        Args:
            api_servers: Mapping of server_id -> server_config
            manufacturer: Manufacturer instance to assign
            options: command options dict with keys 'dry_run' and 'full'

        Returns:
            Tuple of (total_discovered, total_imported, total_updated)
        """
        from micboard.models.locations.structure import Location
        from micboard.services.integrations.api_server_service import (
            APIServerConnectionService,
            sanitized_api_exception_info,
        )

        total_discovered = 0
        total_imported = 0
        total_updated = 0

        for server_id, server_config in api_servers.items():
            try:
                server_manufacturer = str(server_config.get("manufacturer", "shure")).lower()
                if server_manufacturer != "shure":
                    logger.info(
                        "Skipping unsupported manufacturer %s for server %s",
                        server_manufacturer,
                        server_id,
                    )
                    continue

                devices = APIServerConnectionService.fetch_shure_devices(
                    base_url=server_config["base_url"],
                    shared_key=server_config["shared_key"],
                )
                total_discovered += len(devices) if devices else 0

                # Resolve location if provided on server config
                location = None
                if server_config.get("location_id"):
                    try:
                        location = Location.objects.get(id=server_config["location_id"])
                    except Location.DoesNotExist:
                        location = None

                for device in devices or []:
                    try:
                        created, updated = self.import_device(
                            device=device,
                            manufacturer=manufacturer,
                            location=location,
                            server_id=server_id,
                            dry_run=options.get("dry_run", False),
                            full=options.get("full", False),
                        )
                        if created:
                            total_imported += 1
                        if updated:
                            total_updated += 1
                    except Exception as exc:
                        logger.exception(
                            "Error importing device from %s",
                            server_id,
                            exc_info=sanitized_api_exception_info(exc),
                        )
                        continue

            except Exception as exc:
                logger.exception(
                    "Failed to connect to server %s",
                    server_id,
                    exc_info=sanitized_api_exception_info(exc),
                )
                continue

        return total_discovered, total_imported, total_updated
