"""Device synchronization operations for manufacturers.

Writes device data from manufacturer APIs to the local database,
handling normalization, deduplication, chassis creation and updates.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from micboard.services.manufacturer.plugin_registry import PluginRegistry

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
    ) -> dict[str, Any]:
        """Synchronize all devices from a manufacturer.

        Polls the manufacturer API and updates local models.

        Args:
            manufacturer_code: Manufacturer code.
            organization_id: Optional organization ID for MSP mode.
            campus_id: Optional campus ID for MSP mode.

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

        try:
            manufacturer = Manufacturer.objects.get(code=manufacturer_code)
        except Manufacturer.DoesNotExist:
            return {
                "success": False,
                "devices_added": 0,
                "devices_updated": 0,
                "devices_removed": 0,
                "errors": [f"Manufacturer not found: {manufacturer_code}"],
            }

        plugin = PluginRegistry.get_plugin(manufacturer_code)
        if not plugin:
            return {
                "success": False,
                "devices_added": 0,
                "devices_updated": 0,
                "devices_removed": 0,
                "errors": [f"Plugin not found: {manufacturer_code}"],
            }

        try:
            api_devices = plugin.get_devices() or []
            normalized_devices = ManufacturerSyncService._normalize_devices(api_devices, plugin)

            if not normalized_devices:
                return {
                    "success": True,
                    "devices_added": 0,
                    "devices_updated": 0,
                    "devices_removed": 0,
                    "errors": [],
                }

            created_count = 0
            updated_count = 0

            for payload in normalized_devices:
                outcome = ManufacturerSyncService._sync_normalized_device(
                    payload, manufacturer, check_device
                )
                if outcome == "created":
                    created_count += 1
                elif outcome == "updated":
                    updated_count += 1

            return {
                "success": True,
                "devices_added": created_count,
                "devices_updated": updated_count,
                "devices_removed": 0,
                "errors": [],
            }

        except Exception as e:
            return {
                "success": False,
                "devices_added": 0,
                "devices_updated": 0,
                "devices_removed": 0,
                "errors": [str(e)],
            }

    @staticmethod
    def _sync_normalized_device(payload, manufacturer, check_device) -> str | None:
        """Persist one normalized device and return its sync outcome."""
        dedup_result = check_device(
            serial_number=payload.serial_number or None,
            mac_address=payload.mac_address or None,
            ip=payload.ip,
            api_device_id=payload.api_device_id,
            manufacturer=manufacturer,
        )
        if dedup_result.is_conflict:
            return None

        if dedup_result.is_moved and dedup_result.existing_device:
            existing = dedup_result.existing_device
            ManufacturerSyncService._update_existing_chassis(existing, payload, set_ip=True)
            ManufacturerSyncService._mark_chassis_online(existing)
            return "updated"

        if dedup_result.is_duplicate and dedup_result.existing_device:
            existing = dedup_result.existing_device
            ManufacturerSyncService._update_existing_chassis(existing, payload)
            if existing.status not in {"online", "degraded", "maintenance"}:
                ManufacturerSyncService._mark_chassis_online(existing)
            return "updated"

        if dedup_result.is_new:
            chassis = ManufacturerSyncService._create_chassis(payload, manufacturer)
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
            mac_address=payload.mac_address,
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

    @staticmethod
    async def async_sync_devices_for_manufacturer(*, manufacturer_code: str):
        """Async: Sync devices for a manufacturer.

        Args:
            manufacturer_code: Manufacturer code (e.g., 'shure', 'sennheiser')

        Returns:
            Sync result dictionary with success status, counts, and errors
        """
        from asgiref.sync import sync_to_async

        return await sync_to_async(ManufacturerSyncService.sync_devices_for_manufacturer)(
            manufacturer_code=manufacturer_code
        )
