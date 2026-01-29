"""Manufacturer service layer for device synchronization and plugin management.

Orchestrates communication with manufacturer APIs via the plugin architecture.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

from django.db.models import QuerySet
from django.utils import timezone

from micboard.models import ManufacturerConfiguration
from micboard.services.plugin_registry import PluginRegistry

if TYPE_CHECKING:
    from micboard.manufacturers.base import ManufacturerPlugin


class ManufacturerService:
    """Business logic for manufacturer API interactions and device synchronization."""

    @staticmethod
    def get_plugin(*, manufacturer_code: str) -> ManufacturerPlugin | None:
        """Retrieve a manufacturer plugin by code.

        Args:
            manufacturer_code: Manufacturer code (e.g., 'shure', 'sennheiser').

        Returns:
            ManufacturerPlugin instance or None if not found.
        """
        return PluginRegistry.get_plugin(manufacturer_code)

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
        from micboard.models import Manufacturer
        from micboard.services.hardware_deduplication_service import (
            get_hardware_deduplication_service,
        )
        from micboard.services.hardware_lifecycle import get_lifecycle_manager

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

        plugin = ManufacturerService.get_plugin(manufacturer_code=manufacturer_code)
        if not plugin:
            return {
                "success": False,
                "devices_added": 0,
                "devices_updated": 0,
                "devices_removed": 0,
                "errors": [f"Plugin not found: {manufacturer_code}"],
            }

        try:
            # Get devices from API
            api_devices = plugin.get_devices() or []
            normalized_devices = ManufacturerService._normalize_devices(api_devices, plugin)

            if not normalized_devices:
                return {
                    "success": True,
                    "devices_added": 0,
                    "devices_updated": 0,
                    "devices_removed": 0,
                    "errors": [],
                }

            dedup_service = get_hardware_deduplication_service(manufacturer)
            lifecycle = get_lifecycle_manager(manufacturer.code)

            created_count = 0
            updated_count = 0

            for payload in normalized_devices:
                dedup_result = dedup_service.check_device(
                    serial_number=payload.serial_number or None,
                    mac_address=payload.mac_address or None,
                    ip=payload.ip,
                    api_device_id=payload.api_device_id,
                    manufacturer=manufacturer,
                )

                if dedup_result.is_conflict:
                    # Queue for approval
                    continue

                if dedup_result.is_moved and dedup_result.existing_device:
                    existing = dedup_result.existing_device
                    ManufacturerService._update_existing_chassis(existing, payload, set_ip=True)
                    lifecycle.mark_online(existing)
                    updated_count += 1
                    continue

                if dedup_result.is_duplicate and dedup_result.existing_device:
                    existing = dedup_result.existing_device
                    ManufacturerService._update_existing_chassis(existing, payload)
                    if existing.status not in {"online", "degraded", "maintenance"}:
                        lifecycle.mark_online(existing)
                    updated_count += 1
                    continue

                if dedup_result.is_new:
                    chassis = ManufacturerService._create_chassis(payload, manufacturer)
                    lifecycle.mark_online(chassis)
                    created_count += 1

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
    def _normalize_devices(api_devices: Iterable[dict[str, Any]], plugin) -> list[dict[str, Any]]:
        """Normalize and validate raw API device payloads."""
        from micboard.services.hardware import NormalizedHardware

        normalized: list[NormalizedHardware] = []
        for raw in api_devices:
            # Transform using plugin first
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
        from django.utils import timezone

        now = timezone.now()

        if set_ip:
            chassis.ip = payload.ip

        chassis.name = payload.name or chassis.name
        chassis.model = payload.model or chassis.model

        # Update role based on device_type if specified
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
        from micboard.models import WirelessChassis

        # Determine role based on device_type or default to receiver
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
    def get_active_manufacturers() -> QuerySet:
        """Get all active manufacturer configurations.

        Returns:
            QuerySet of active ManufacturerConfiguration objects.
        """
        return ManufacturerConfiguration.objects.filter(active=True, enabled=True)

    @staticmethod
    def get_manufacturer_config(*, manufacturer_code: str) -> ManufacturerConfiguration | None:
        """Get configuration for a manufacturer.

        Args:
            manufacturer_code: Manufacturer code.

        Returns:
            ManufacturerConfiguration object or None.
        """
        return ManufacturerConfiguration.objects.filter(
            manufacturer_code=manufacturer_code, active=True, enabled=True
        ).first()

    @staticmethod
    def test_manufacturer_connection(*, manufacturer_code: str) -> dict[str, Any]:
        """Test connectivity to a manufacturer API.

        Args:
            manufacturer_code: Manufacturer code.

        Returns:
            Dictionary with test result:
            {
                'success': bool,
                'message': str,
                'response_time_ms': float | None
            }
        """
        plugin = ManufacturerService.get_plugin(manufacturer_code=manufacturer_code)
        if not plugin:
            return {
                "success": False,
                "message": f"Plugin not found: {manufacturer_code}",
                "response_time_ms": None,
            }

        try:
            result = plugin.test_connection()
            return result
        except Exception as e:
            return {"success": False, "message": str(e), "response_time_ms": None}

    @staticmethod
    def get_device_status(*, manufacturer_code: str, device_id: str) -> dict[str, Any] | None:
        """Get status of a specific device from manufacturer API.

        Args:
            manufacturer_code: Manufacturer code.
            device_id: Device ID in manufacturer system.

        Returns:
            Device status dict or None if not found/error.
        """
        plugin = ManufacturerService.get_plugin(manufacturer_code=manufacturer_code)
        if not plugin:
            return None

        try:
            return plugin.get_device_status(device_id)
        except Exception:
            return None
