"""Service for promoting discovered devices to managed WirelessChassis instances."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from micboard.services.hardware.dtos import WirelessChassisWrite
from micboard.services.hardware.wireless_chassis_persistence_service import (
    WirelessChassisPersistenceService,
)
from micboard.utils.exception_logging import sanitized_exception_info

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

        try:
            existing = self._find_existing_chassis_for_discovered(discovered)
            if existing:
                return (False, f"Device already managed as chassis: {existing}", existing)

            plugin, device_data = self._get_plugin_and_device_data_for_promotion(discovered)
            if not plugin:
                return (False, "Plugin not available for manufacturer", None)

            if not device_data:
                logger.warning(
                    "Could not fetch detailed data for %s from API, creating basic chassis",
                    discovered.ip,
                )
                chassis = WirelessChassisPersistenceService.create(
                    manufacturer=discovered.manufacturer,
                    write=WirelessChassisWrite(
                        api_device_id=discovered.ip,
                        ip=discovered.ip,
                        name=f"{discovered.device_type} at {discovered.ip}",
                        model=discovered.device_type,
                        role="receiver",
                        max_channels=discovered.channels or 4,
                        status="discovered",
                    ),
                )
                return (True, "Created basic chassis (limited API data)", chassis)

            return self._attempt_promotion_with_device_data(discovered, plugin, device_data)

        except Exception as exc:
            logger.exception(
                "Error promoting discovered device %s",
                getattr(discovered, "pk", None),
                exc_info=sanitized_exception_info(exc),
            )
            return (
                False,
                f"Promotion failed ({type(exc).__name__}); details redacted.",
                None,
            )

    def _find_existing_chassis_for_discovered(self, discovered: Any) -> Any:
        from micboard.models.hardware.wireless_chassis import WirelessChassis

        return WirelessChassis.objects.filter(
            ip=discovered.ip, manufacturer=discovered.manufacturer
        ).first()

    def _get_plugin_and_device_data_for_promotion(self, discovered: Any) -> Any:
        from micboard.services.common.base.plugin import build_manufacturer_plugin

        try:
            plugin = build_manufacturer_plugin(discovered.manufacturer)
        except (ImportError, ValueError):
            return None, None

        try:
            api_devices = plugin.get_devices() or []
            for dev in api_devices:
                if dev.get("ip") == discovered.ip or dev.get("ipAddress") == discovered.ip:
                    return plugin, dev
        except Exception as exc:
            logger.exception(
                "Error fetching vendor devices for discovered device %s",
                getattr(discovered, "pk", None),
                exc_info=sanitized_exception_info(exc),
            )

        return plugin, None

    def _attempt_promotion_with_device_data(
        self, discovered: Any, plugin: Any, device_data: Any
    ) -> tuple[bool, str, WirelessChassis | None]:
        from micboard.services.deduplication.check import check_device
        from micboard.services.deduplication.tracking import log_device_movement

        device = plugin.normalize_device(device_data)
        if device is None or not device.ip:
            return (False, "Failed to normalize device data", None)

        dedup_result = check_device(
            serial_number=device.serial_number,
            mac_address=device.mac_address,
            ip=device.ip,
            api_device_id=device.api_device_id,
            manufacturer=discovered.manufacturer,
        )

        if dedup_result.is_conflict:
            return (False, f"Device conflict: {dedup_result.conflict_type}", None)

        chassis = dedup_result.existing_device
        if dedup_result.is_moved and chassis is not None:
            old_ip = str(chassis.ip) if chassis.ip else None
            WirelessChassisPersistenceService.update_from_normalized(
                chassis=chassis,
                payload=device,
                set_ip=True,
            )
            log_device_movement(
                device=chassis,
                old_ip=old_ip,
                new_ip=device.ip,
                detected_by="promotion",
                reason="Promotion matched an existing chassis at a new address",
            )
            return (True, "Updated existing chassis", chassis)

        if dedup_result.is_duplicate and chassis is not None:
            WirelessChassisPersistenceService.update_from_normalized(
                chassis=chassis,
                payload=device,
            )
            return (True, "Updated existing chassis", chassis)

        chassis = WirelessChassisPersistenceService.create_from_normalized(
            payload=device,
            manufacturer=discovered.manufacturer,
        )
        return (True, "Created new managed chassis", chassis)
