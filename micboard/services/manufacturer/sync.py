"""Device synchronization operations for manufacturers.

Writes device data from manufacturer APIs to the local database,
handling normalization, deduplication, chassis creation and updates.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from micboard.services.deduplication.identity_mutation_lock import (
    DeviceIdentityMutationLockService,
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
    from micboard.services.core.hardware import NormalizedHardware

logger = logging.getLogger(__name__)


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
        normalized_devices,
        *,
        manufacturer,
        check_device,
        identity_index_class,
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
        payload,
        manufacturer,
        check_device,
        *,
        identity_index=None,
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
            existing = existing_device
            old_ip = existing.ip if identity_index is not None else None
            ManufacturerSyncService._update_existing_chassis(existing, payload, set_ip=True)
            if identity_index is not None and old_ip is not None:
                identity_index.move_ip(existing, old_ip=old_ip)
            ManufacturerSyncService._mark_chassis_online(existing)
            return "updated"

        if dedup_result.is_duplicate and existing_device:
            existing = existing_device
            ManufacturerSyncService._update_existing_chassis(existing, payload)
            if existing.status not in {"online", "degraded", "maintenance"}:
                ManufacturerSyncService._mark_chassis_online(existing)
            return "updated"

        if dedup_result.is_new:
            chassis = ManufacturerSyncService._create_chassis(payload, manufacturer)
            if identity_index is not None:
                identity_index.add(chassis)
            ManufacturerSyncService._mark_chassis_online(chassis)
            return "created"
        return None

    @staticmethod
    def _mark_chassis_online(chassis) -> None:
        if chassis.status == "online":
            return
        chassis.status = "online"
        chassis.save(update_fields=["status"])

    @staticmethod
    def _normalize_devices(
        api_devices: Iterable[dict[str, Any]], plugin
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

    @staticmethod
    def _update_existing_chassis(chassis, payload, *, set_ip: bool = False):
        """Update an existing WirelessChassis with normalized payload fields."""
        now = timezone.now()

        if set_ip:
            chassis.ip = payload.ip

        chassis.name = payload.name or chassis.name
        chassis.model = payload.model or chassis.model

        if payload.device_type:
            if "transmitter" in payload.device_type.lower():
                chassis.role = "transmitter"
            elif "transceiver" in payload.device_type.lower():
                chassis.role = "transceiver"
            else:
                chassis.role = "receiver"

        chassis.firmware_version = payload.firmware_version or chassis.firmware_version
        chassis.hosted_firmware_version = (
            payload.hosted_firmware_version or chassis.hosted_firmware_version
        )
        chassis.description = payload.description or chassis.description
        chassis.subnet_mask = payload.subnet_mask or chassis.subnet_mask
        chassis.gateway = payload.gateway or chassis.gateway
        chassis.network_mode = payload.network_mode or chassis.network_mode
        chassis.interface_id = payload.interface_id or chassis.interface_id
        chassis.last_seen = now
        update_fields = [
            "name",
            "model",
            "role",
            "firmware_version",
            "hosted_firmware_version",
            "description",
            "subnet_mask",
            "gateway",
            "network_mode",
            "interface_id",
            "last_seen",
            "updated_at",
        ]
        incoming_mac = canonicalize_mac_address(payload.mac_address)
        existing_mac = canonicalize_mac_address(getattr(chassis, "mac_address", None))
        if incoming_mac and incoming_mac == existing_mac and chassis.mac_address != incoming_mac:
            chassis.mac_address = incoming_mac
            update_fields.append("mac_address")
        if set_ip:
            update_fields.insert(0, "ip")

        chassis.save(update_fields=update_fields)
        return chassis

    @staticmethod
    def _create_chassis(payload, manufacturer):
        """Persist a new chassis/base station from a normalized payload."""
        from micboard.models.hardware.wireless_chassis import WirelessChassis

        role = "receiver"
        if payload.device_type and "transmitter" in payload.device_type.lower():
            role = "transmitter"
        elif payload.device_type and "transceiver" in payload.device_type.lower():
            role = "transceiver"

        return WirelessChassis.objects.create(
            manufacturer=manufacturer,
            api_device_id=payload.api_device_id,
            serial_number=payload.serial_number,
            mac_address=canonicalize_mac_address(payload.mac_address),
            ip=payload.ip,
            name=payload.name,
            model=payload.model,
            role=role,
            firmware_version=payload.firmware_version,
            hosted_firmware_version=payload.hosted_firmware_version,
            description=payload.description,
            subnet_mask=payload.subnet_mask,
            gateway=payload.gateway,
            network_mode=payload.network_mode,
            interface_id=payload.interface_id,
            last_seen=timezone.now(),
        )
