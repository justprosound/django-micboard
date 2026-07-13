"""Service for promoting discovered devices to managed WirelessChassis instances."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from micboard.models.discovery.registry import DiscoveredDevice
    from micboard.models.hardware.wireless_chassis import WirelessChassis

logger = logging.getLogger(__name__)


class DevicePromotionService:
    """Promotes discovered devices to managed WirelessChassis records."""

    def promote_discovered_device(
        self,
        discovered: DiscoveredDevice,
    ) -> tuple[bool, str, WirelessChassis | None]:
        """Promote a discovered device to a managed WirelessChassis.

        Returns a tuple (success, message, chassis_or_none).
        """
        if not discovered.manufacturer:
            return (False, "No manufacturer specified for discovered device", None)

        existing = self._find_existing_chassis_for_discovered(discovered)
        if existing:
            return (False, f"Device already managed as chassis: {existing}", existing)

        try:
            plugin, device_data = self._get_plugin_and_device_data_for_promotion(discovered)
            if not plugin:
                return (False, "Plugin not available for manufacturer", None)

            if not device_data:
                chassis = self._create_basic_chassis_from_discovered(discovered)
                return (True, "Created basic chassis (limited API data)", chassis)

            return self._attempt_promotion_with_device_data(discovered, plugin, device_data)

        except Exception as e:
            logger.exception("Error promoting discovered device %s", discovered.ip)
            return (False, f"Exception during promotion: {e}", None)

    def _find_existing_chassis_for_discovered(self, discovered):
        from micboard.models.hardware.wireless_chassis import WirelessChassis

        return WirelessChassis.objects.filter(
            ip=discovered.ip, manufacturer=discovered.manufacturer
        ).first()

    def _get_plugin_and_device_data_for_promotion(self, discovered):
        from micboard.services.manufacturer.plugin_registry import PluginRegistry

        plugin = PluginRegistry.get_plugin(discovered.manufacturer.code, discovered.manufacturer)
        if not plugin:
            return None, None

        try:
            api_devices = plugin.get_devices() or []
            for dev in api_devices:
                if dev.get("ip") == discovered.ip or dev.get("ipAddress") == discovered.ip:
                    return plugin, dev
        except Exception:
            logger.exception("Error fetching devices from plugin for promotion: %s", discovered.ip)

        return plugin, None

    def _create_basic_chassis_from_discovered(self, discovered):
        from micboard.models.hardware.wireless_chassis import WirelessChassis

        logger.warning(
            "Could not fetch detailed data for %s from API, creating basic chassis",
            discovered.ip,
        )
        return WirelessChassis.objects.create(
            manufacturer=discovered.manufacturer,
            api_device_id=discovered.ip,
            ip=discovered.ip,
            name=f"{discovered.device_type} at {discovered.ip}",
            model=discovered.device_type,
            role="receiver",
            max_channels=discovered.channels or 4,
            status="discovered",
        )

    def _attempt_promotion_with_device_data(
        self, discovered, plugin, device_data
    ) -> tuple[bool, str, WirelessChassis | None]:
        from micboard.services.deduplication.check import check_device
        from micboard.services.manufacturer.sync import ManufacturerSyncService

        transformed = plugin.transform_device_data(device_data)
        if not transformed:
            return (False, "Failed to transform device data", None)

        dedup_result = check_device(
            serial_number=transformed.get("serial_number"),
            mac_address=transformed.get("mac_address"),
            ip=transformed.get("ip"),
            api_device_id=transformed.get("api_device_id"),
            manufacturer=discovered.manufacturer,
        )

        if dedup_result.is_conflict:
            return (False, f"Device conflict: {dedup_result.conflict_type}", None)

        if dedup_result.is_duplicate and dedup_result.existing_device:
            chassis = dedup_result.existing_device
            normalized = ManufacturerSyncService._normalize_devices([device_data], plugin)
            if not normalized:
                return (False, "Failed to normalize duplicate device data", None)
            ManufacturerSyncService._update_existing_chassis(
                chassis,
                normalized[0],
            )
            return (True, "Updated existing chassis", chassis)

        normalized = ManufacturerSyncService._normalize_devices([device_data], plugin)
        if normalized:
            chassis = ManufacturerSyncService._create_chassis(
                normalized[0], discovered.manufacturer
            )
            return (True, "Created new managed chassis", chassis)

        return (False, "Failed to normalize device data", None)
