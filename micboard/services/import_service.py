"""Service to import devices into WirelessChassis models.

This encapsulates the device import/update logic previously embedded in the
management command to make it reusable and easier to test.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from micboard.services.core.hardware_lifecycle import (
    HardwareLifecycleManager,
    HardwareStatus,
    map_api_state_to_status,
)
from micboard.services.deduplication.check import check_device
from micboard.services.deduplication.identity_mutation_lock import (
    DeviceIdentityMutationLockService,
)
from micboard.services.hardware.dtos import WirelessChassisWrite
from micboard.services.hardware.wireless_chassis_persistence_service import (
    WirelessChassisPersistenceService,
)
from micboard.utils.mac_address import canonicalize_mac_address

if TYPE_CHECKING:
    from micboard.models.discovery.manufacturer import Manufacturer
    from micboard.models.hardware.wireless_chassis import WirelessChassis
    from micboard.models.locations.structure import Location

logger = logging.getLogger(__name__)


class ImportService:
    """Service responsible for importing a single device payload into the DB."""

    @staticmethod
    def _reconcile_status(
        chassis: WirelessChassis,
        target_status: str,
        *,
        server_id: str | None,
    ) -> None:
        """Apply an imported status through valid lifecycle transitions."""
        transition_statuses = [target_status]
        if (
            chassis.status == HardwareStatus.DISCOVERED.value
            and target_status == HardwareStatus.ONLINE.value
        ):
            transition_statuses.insert(0, HardwareStatus.PROVISIONING.value)

        lifecycle = HardwareLifecycleManager()
        metadata = {
            "source": "import",
            "server_id": server_id,
            "target_status": target_status,
        }
        for next_status in transition_statuses:
            if lifecycle.transition_device(
                chassis,
                next_status,
                reason="Device state received during import",
                metadata=metadata,
            ):
                continue
            raise RuntimeError(
                f"Lifecycle rejected imported status transition to {next_status!r} "
                f"for chassis {chassis.pk}"
            )

    def import_device(
        self,
        device: dict[str, Any],
        manufacturer: Manufacturer,
        location: Location | None = None,
        server_id: str | None = None,
        dry_run: bool = False,
        full: bool = False,
    ) -> tuple[bool, bool]:
        """Import or update a single device.

        Returns a tuple (created: bool, updated: bool).
        """
        del full
        raw_serial = device.get("serial") or device.get("serialNumber")
        model = device.get("model") or device.get("deviceType")
        raw_ip = device.get("ip") or device.get("ipAddress")
        raw_mac = device.get("mac") or device.get("macAddress")
        raw_api_device_id = device.get("id") or device.get("deviceId")
        device_type = device.get("type", "UNKNOWN")

        serial = str(raw_serial).strip() if raw_serial is not None else ""
        ip = str(raw_ip).strip() if raw_ip is not None else ""
        api_device_id = str(raw_api_device_id).strip() if raw_api_device_id is not None else ""
        mac = canonicalize_mac_address(str(raw_mac)) if raw_mac is not None else None

        if not serial or not ip or not api_device_id:
            return False, False

        role = self._device_role(device_type)

        status = map_api_state_to_status(
            str(device.get("state") or "UNKNOWN").upper(),
            "discovered",
        )

        with DeviceIdentityMutationLockService.acquire(
            manufacturer=manufacturer
        ) as locked_manufacturer:
            deduplication = check_device(
                serial_number=serial,
                mac_address=mac,
                ip=ip,
                api_device_id=api_device_id,
                manufacturer=locked_manufacturer,
            )
            if deduplication.is_conflict:
                return False, False

            chassis = deduplication.existing_device
            if chassis is not None and chassis.manufacturer_id != locked_manufacturer.pk:
                return False, False
            if dry_run:
                return (chassis is None, chassis is not None)

            if chassis is None:
                WirelessChassisPersistenceService.create(
                    manufacturer=locked_manufacturer,
                    write=WirelessChassisWrite(
                        serial_number=serial,
                        model=model or "Unknown",
                        role=role,
                        ip=ip,
                        mac_address=mac,
                        location=location,
                        status=status,
                        is_online=status == "online",
                        api_device_id=api_device_id,
                    ),
                )
                return True, False

            metadata_write = WirelessChassisWrite(
                model=model or "Unknown",
                role=role,
                ip=ip,
                location=location,
                api_device_id=api_device_id,
            )
            if mac is not None:
                metadata_write = metadata_write.model_copy(update={"mac_address": mac})
            WirelessChassisPersistenceService.update(
                chassis=chassis,
                write=metadata_write,
            )

            if status != chassis.status:
                self._reconcile_status(
                    chassis,
                    status,
                    server_id=server_id,
                )
            return False, True

    @staticmethod
    def _device_role(device_type: object) -> str:
        """Map untrusted manufacturer type text to one supported chassis role."""
        normalized = device_type.lower() if isinstance(device_type, str) else ""
        if "transmitter" in normalized:
            return "transmitter"
        if "transceiver" in normalized:
            return "transceiver"
        return "receiver"

    def import_from_servers(
        self,
        api_servers: dict[str, dict[str, Any]],
        manufacturer: Manufacturer,
        options: dict[str, Any],
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
        from micboard.services.integrations.api_server_service import APIServerConnectionService
        from micboard.utils.exception_logging import sanitized_exception_info

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
                            exc_info=sanitized_exception_info(exc),
                        )
                        continue

            except Exception as exc:
                logger.exception(
                    "Failed to connect to server %s",
                    server_id,
                    exc_info=sanitized_exception_info(exc),
                )
                continue

        return total_discovered, total_imported, total_updated
