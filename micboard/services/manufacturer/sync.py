"""Device synchronization operations for manufacturers.

Writes device data from manufacturer APIs to the local database,
handling normalization, deduplication, chassis creation and updates.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from micboard.services.core.hardware_lifecycle import HardwareLifecycleManager, HardwareStatus
from micboard.services.deduplication.identity_mutation_lock import (
    DeviceIdentityMutationLockService,
)
from micboard.services.deduplication.tracking import log_device_movement
from micboard.services.hardware.wireless_chassis_persistence_service import (
    WirelessChassisPersistenceService,
)
from micboard.services.manufacturer.plugin_registry import PluginRegistry
from micboard.services.sync.discovery_trigger_service import coalesce_discovery_scheduling
from micboard.services.sync.polling_dtos import (
    ManufacturerPollLimits,
    ManufacturerSyncResult,
    VendorInventoryBatch,
)
from micboard.utils.exception_logging import sanitized_exception_info
from micboard.utils.mac_address import canonicalize_mac_address

if TYPE_CHECKING:
    from micboard.models.discovery.manufacturer import Manufacturer
    from micboard.models.hardware.wireless_chassis import WirelessChassis
    from micboard.services.core.hardware import NormalizedHardware
    from micboard.services.deduplication.identity_index import DeviceIdentityIndex

logger = logging.getLogger(__name__)


def _transition_responding_chassis_online(
    chassis: WirelessChassis,
    *,
    manufacturer: Manufacturer,
) -> None:
    """Move a responding chassis online through valid lifecycle transitions."""
    if chassis.status == HardwareStatus.ONLINE:
        return

    lifecycle = HardwareLifecycleManager()
    if chassis.status == HardwareStatus.DISCOVERED and not lifecycle.transition_device(
        chassis,
        HardwareStatus.PROVISIONING,
        reason="Device responding during manufacturer synchronization",
    ):
        raise RuntimeError(f"Could not provision wireless chassis {chassis.pk}")
    if not lifecycle.mark_online(chassis):
        raise RuntimeError(f"Could not mark wireless chassis {chassis.pk} online")
    chassis.refresh_from_db(fields=["status", "is_online", "last_online_at", "last_seen"])


def _persist_moved_chassis(
    *,
    chassis: WirelessChassis,
    payload: NormalizedHardware,
    manufacturer: Manufacturer,
    identity_index: DeviceIdentityIndex | None,
) -> None:
    """Persist an address move and keep the batch identity index current."""
    old_ip = str(chassis.ip) if chassis.ip else None
    WirelessChassisPersistenceService.update_from_normalized(
        chassis=chassis,
        payload=payload,
        set_ip=True,
    )
    new_ip = str(chassis.ip) if chassis.ip else None
    if old_ip != new_ip:
        log_device_movement(
            device=chassis,
            old_ip=old_ip,
            new_ip=new_ip,
            detected_by="manufacturer_sync",
            reason="Manufacturer synchronization detected an address change",
        )
    if identity_index is not None and old_ip is not None:
        identity_index.move_ip(chassis, old_ip=old_ip)
    _transition_responding_chassis_online(
        chassis,
        manufacturer=manufacturer,
    )


class ManufacturerSyncService:
    """Write operations for manufacturer device synchronization."""

    @staticmethod
    def sync_devices_for_manufacturer(
        *,
        manufacturer_code: str,
        organization_id: int | None = None,
        campus_id: int | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Synchronize all devices from a manufacturer.

        Polls the manufacturer API and updates local models.

        Args:
            manufacturer_code: Manufacturer code.
            organization_id: Optional organization ID for MSP mode.
            campus_id: Optional campus ID for MSP mode.
            force: Permit an explicitly requested operator poll while inactive.

        Returns:
            Dictionary with sync status and counts:
            {
                'success': bool,
                'devices_added': int,
                'devices_updated': int,
                'devices_removed': int,
                'errors': list[str]
            }
        """
        from micboard.models.discovery.manufacturer import Manufacturer
        from micboard.services.deduplication.check import check_device
        from micboard.services.deduplication.identity_index import DeviceIdentityIndex

        limits = ManufacturerPollLimits.from_settings()

        manufacturer_filters: dict[str, str | bool] = {"code": manufacturer_code}
        if not force:
            manufacturer_filters["is_active"] = True
        try:
            manufacturer = Manufacturer.objects.get(**manufacturer_filters)
        except Manufacturer.DoesNotExist:
            return ManufacturerSyncResult(
                success=False,
                errors=[f"Manufacturer not found or inactive: {manufacturer_code}"],
                device_limit=limits.max_devices,
            ).as_dict()

        plugin = PluginRegistry.get_plugin(manufacturer_code)
        if not plugin:
            return ManufacturerSyncResult(
                success=False,
                errors=[f"Plugin not found: {manufacturer_code}"],
                device_limit=limits.max_devices,
            ).as_dict()

        try:
            api_devices = plugin.get_devices() or ()
            inventory = VendorInventoryBatch.consume(
                api_devices,
                device_limit=limits.max_devices,
            )
            if not inventory.inventory_complete:
                return ManufacturerSyncResult(
                    success=False,
                    errors=[
                        "Manufacturer inventory exceeded the configured device limit; "
                        "no devices were synchronized."
                    ],
                    devices_examined=len(inventory.devices),
                    device_limit=limits.max_devices,
                    inventory_complete=False,
                ).as_dict()

            normalized_devices = ManufacturerSyncService._normalize_devices(
                inventory.devices,
                plugin,
            )

            if not normalized_devices:
                return ManufacturerSyncResult(
                    success=True,
                    devices_examined=len(inventory.devices),
                    device_limit=limits.max_devices,
                ).as_dict()

            persisted_counts = ManufacturerSyncService._persist_normalized_devices(
                normalized_devices,
                manufacturer=manufacturer,
                check_device=check_device,
                identity_index_class=DeviceIdentityIndex,
                force=force,
            )
            if persisted_counts is None:
                return ManufacturerSyncResult(
                    success=False,
                    errors=[
                        "Manufacturer became inactive during polling; no devices were synchronized."
                    ],
                    devices_examined=len(inventory.devices),
                    device_limit=limits.max_devices,
                ).as_dict()
            created_count, updated_count = persisted_counts

            return ManufacturerSyncResult(
                success=True,
                devices_added=created_count,
                devices_updated=updated_count,
                devices_examined=len(inventory.devices),
                device_limit=limits.max_devices,
            ).as_dict()

        except Exception as exc:
            logger.exception(
                "Manufacturer device synchronization failed for %s",
                manufacturer_code,
                exc_info=sanitized_exception_info(exc),
            )
            return ManufacturerSyncResult(
                success=False,
                errors=[f"Device synchronization failed ({type(exc).__name__}); details redacted."],
                device_limit=limits.max_devices,
            ).as_dict()

    @staticmethod
    def _persist_normalized_devices(
        normalized_devices: Any,
        *,
        manufacturer: Any,
        check_device: Any,
        identity_index_class: Any,
        force: bool = False,
    ) -> tuple[int, int] | None:
        """Serialize identity reads and writes across manufacturer pollers."""
        created_count = 0
        updated_count = 0
        with DeviceIdentityMutationLockService.acquire(
            manufacturer=manufacturer
        ) as locked_manufacturer:
            if not force and not locked_manufacturer.is_active:
                logger.info(
                    "Manufacturer synchronization stopped after deactivation for ID %s",
                    locked_manufacturer.pk,
                )
                return None
            identity_index = identity_index_class.build(
                normalized_devices,
                manufacturer=locked_manufacturer,
            )
            with coalesce_discovery_scheduling():
                for payload in normalized_devices:
                    outcome = ManufacturerSyncService._sync_normalized_device(
                        payload,
                        locked_manufacturer,
                        check_device,
                        identity_index=identity_index,
                    )
                    if outcome == "created":
                        created_count += 1
                    elif outcome == "updated":
                        updated_count += 1
        return created_count, updated_count

    @staticmethod
    def _sync_normalized_device(
        payload: Any,
        manufacturer: Any,
        check_device: Any,
        *,
        identity_index: Any = None,
    ) -> str | None:
        """Persist one normalized device and return its sync outcome."""
        deduplication_kwargs = {
            "serial_number": payload.serial_number or None,
            "mac_address": canonicalize_mac_address(payload.mac_address) or None,
            "ip": payload.ip,
            "api_device_id": payload.api_device_id,
            "manufacturer": manufacturer,
        }
        if identity_index is not None:
            deduplication_kwargs["identity_index"] = identity_index
        dedup_result = check_device(
            **deduplication_kwargs,
        )
        if dedup_result.is_conflict:
            return None

        existing_device = dedup_result.existing_device
        if existing_device is not None and existing_device.manufacturer_id != manufacturer.pk:
            logger.warning(
                "Rejected cross-manufacturer synchronization candidate "
                "(device_id=%s, existing_manufacturer_id=%s, new_manufacturer_id=%s)",
                existing_device.pk,
                existing_device.manufacturer_id,
                manufacturer.pk,
            )
            return None

        if dedup_result.is_moved and existing_device:
            _persist_moved_chassis(
                chassis=existing_device,
                payload=payload,
                manufacturer=manufacturer,
                identity_index=identity_index,
            )
            return "updated"

        if dedup_result.is_duplicate and existing_device:
            existing = existing_device
            WirelessChassisPersistenceService.update_from_normalized(
                chassis=existing,
                payload=payload,
            )
            if existing.status not in {HardwareStatus.DEGRADED, HardwareStatus.MAINTENANCE}:
                _transition_responding_chassis_online(
                    existing,
                    manufacturer=manufacturer,
                )
            return "updated"

        if dedup_result.is_new:
            chassis = WirelessChassisPersistenceService.create_from_normalized(
                payload=payload,
                manufacturer=manufacturer,
                initial_status=HardwareStatus.ONLINE,
            )
            if identity_index is not None:
                identity_index.add(chassis)
            return "created"
        return None

    @staticmethod
    def _normalize_devices(
        api_devices: Iterable[dict[str, Any]], plugin: Any
    ) -> list[NormalizedHardware]:
        """Normalize and validate raw API device payloads."""
        from micboard.services.core.hardware import NormalizedHardware

        normalized: list[NormalizedHardware] = []
        for raw in api_devices:
            transformed = plugin.transform_device_data(raw)
            if not transformed:
                continue

            payload = NormalizedHardware.from_api(transformed)
            if not payload:
                continue
            normalized.append(payload)
        return normalized
