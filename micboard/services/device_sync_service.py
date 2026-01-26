"""Device synchronization service.

Handles core logic for syncing device data from manufacturer APIs.
Previously scattered across signal handlers and views.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.utils import timezone

if TYPE_CHECKING:
    from micboard.models import (
        Manufacturer,
        WirelessChassis,
        WirelessUnit,
    )

logger = logging.getLogger(__name__)


class DeviceSyncService:
    """Orchestrates device synchronization from manufacturer APIs.

    Replaces scattered signal logic with testable service methods.
    """

    @staticmethod
    def sync_device_status(
        *,
        device_obj: WirelessChassis,
        online: bool,
        organization_id: int | None = None,
        **extra_data: Any,
    ) -> bool:
        """Update device online status with audit logging.

        Args:
            device_obj: WirelessChassis instance to update
            online: New online status
            organization_id: Optional org context (for audit)
            **extra_data: Additional status data to log

        Returns:
            True if status changed, False otherwise
        """
        old_status = device_obj.is_online
        device_obj.is_online = online
        device_obj.last_seen = timezone.now()

        # Also update status string
        if online:
            if device_obj.status == "offline":
                device_obj.status = "online"
        else:
            device_obj.status = "offline"

        if device_obj.is_online != old_status:
            device_obj.save(update_fields=["is_online", "status", "last_seen", "updated_at"])
            logger.info(
                "Device status changed: %s → %s (org=%s)",
                device_obj.name,
                "online" if online else "offline",
                organization_id or "default",
            )
            return True
        return False

    @staticmethod
    def sync_device_battery(
        *,
        device_obj: WirelessUnit,
        battery_level: int | None,
        organization_id: int | None = None,
    ) -> bool:
        """Update field unit battery level.

        Args:
            device_obj: WirelessUnit instance
            battery_level: Battery level (raw value 0-255)
            organization_id: Optional org context

        Returns:
            True if battery changed, False otherwise
        """
        if not hasattr(device_obj, "battery"):
            return False

        old_battery = device_obj.battery
        device_obj.battery = battery_level or 255  # 255 is unknown

        if device_obj.battery != old_battery:
            device_obj.save(update_fields=["battery", "updated_at"])
            logger.debug(
                "Device battery updated: %s = %s (org=%s)",
                device_obj.name,
                battery_level,
                organization_id or "default",
            )
            return True
        return False

    @staticmethod
    def bulk_sync_devices(
        *,
        manufacturer: Manufacturer,
        devices_data: list[dict[str, Any]],
        organization_id: int | None = None,
    ) -> dict[str, Any]:
        """Synchronize multiple chassis from API data.

        Args:
            manufacturer: Manufacturer instance
            devices_data: List of device data dicts from API
            organization_id: Optional org context

        Returns:
            Summary dict: {added, updated, removed, errors}
        """
        from micboard.models import WirelessChassis
        from micboard.services.deduplication_service import get_deduplication_service

        stats = {"added": 0, "updated": 0, "removed": 0, "errors": []}

        if not devices_data:
            return stats

        dedup_service = get_deduplication_service()

        for device_data in devices_data:
            try:
                device_id = device_data.get("id") or device_data.get("api_device_id")
                if not device_id:
                    stats["errors"].append("Missing device ID")
                    continue

                # Check for duplicates
                duplicate_chassis = dedup_service.find_duplicate(device_data, manufacturer)

                if duplicate_chassis and duplicate_chassis.api_device_id != device_id:
                    logger.warning(
                        "Duplicate device detected: %s (existing: %s)",
                        device_id,
                        duplicate_chassis.api_device_id,
                    )
                    continue

                # Create or update chassis
                chassis, created = WirelessChassis.objects.update_or_create(
                    manufacturer=manufacturer,
                    api_device_id=device_id,
                    defaults={
                        "name": device_data.get("name", ""),
                        "role": device_data.get("role", "receiver"),
                        "model": device_data.get("model", ""),
                        "ip": device_data.get("ip", ""),
                        "firmware_version": device_data.get("firmware", ""),
                        "is_online": True,
                        "status": "online",
                        "last_seen": timezone.now(),
                    },
                )

                # Ensure channels match model capacity
                if created:
                    chassis.ensure_channel_count()

                if created:
                    stats["added"] += 1
                else:
                    stats["updated"] += 1

            except Exception as e:
                logger.exception("Error syncing device %s: %s", device_id, e)
                stats["errors"].append(str(e))

        return stats

    @staticmethod
    def clear_sync_cache(
        *,
        manufacturer_code: str | None = None,
        organization_id: int | None = None,
    ) -> None:
        """Clear cache entries for synced devices.

        Args:
            manufacturer_code: Optional specific manufacturer
            organization_id: Optional org context
        """
        from django.core.cache import cache

        cache_keys = [
            f"devices_{manufacturer_code or '*'}_{organization_id or '*'}",
            f"discovery_data_{manufacturer_code or '*'}",
            "micboard_device_data",
        ]

        for key in cache_keys:
            cache.delete(key)
            logger.debug("Cleared cache: %s", key)
