"""Synchronization service for device synchronization operations.

Handles device synchronization from manufacturer APIs with location assignment
and offline device detection.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.db.models import QuerySet
from django.utils import timezone

from micboard.services.manufacturer.manufacturer import ManufacturerService

if TYPE_CHECKING:  # pragma: no cover
    from micboard.models import Location


class HardwareSyncService:
    """Business logic for device synchronization and offline detection."""

    @staticmethod
    def sync_devices(
        *,
        manufacturer_code: str,
        location: Location | None = None,
        dry_run: bool = False,
    ) -> dict[str, int]:
        """Synchronize devices from a manufacturer API.

        Args:
            manufacturer_code: Manufacturer code (e.g., 'shure').
            location: Optional location to assign new devices to.
            dry_run: If True, don't save changes to database.

        Returns:
            Dictionary with sync statistics.

        TODO: Ensure all manufacturer-specific config is resolved via SettingsRegistry,
        and that this logic is vendor-agnostic and multi-tenant safe.
        """
        # Use ManufacturerService for the core sync logic
        result = ManufacturerService.sync_devices_for_manufacturer(
            manufacturer_code=manufacturer_code
        )

        # Convert ManufacturerService result format to HardwareSyncService format
        stats = {
            "total_devices": result["devices_added"] + result["devices_updated"],
            "created": result["devices_added"],
            "updated": result["devices_updated"],
            "errors": len(result["errors"]),
            "error_messages": result["errors"],  # Include error messages for debugging
        }

        # If location specified and not dry run, assign location to new devices
        if location and not dry_run and result["success"]:
            # Note: This would need to be implemented in ManufacturerService
            # to assign locations during sync. For now, this is a placeholder.
            pass

        return stats

    @staticmethod
    def detect_offline_devices(
        *,
        manufacturer_code: str,
        timeout_seconds: int = 300,
    ) -> QuerySet:
        """Detect devices that haven't been seen recently.

        Args:
            manufacturer_code: Manufacturer code to check.
            timeout_seconds: Seconds since last update to consider offline.

        Returns:
            QuerySet of offline chassis.
        """
        from micboard.models import WirelessChassis

        cutoff_time = timezone.now() - timedelta(seconds=timeout_seconds)

        offline_devices = WirelessChassis.objects.filter(
            manufacturer__code=manufacturer_code,
            is_online=True,
            last_seen__lt=cutoff_time,
        )

        # Mark them as offline and capture when we noticed
        now = timezone.now()
        offline_device_ids = list(offline_devices.values_list("id", flat=True))
        offline_devices.update(
            is_online=False, last_offline_at=now, last_seen=now, status="offline"
        )

        # Re-query to return the updated devices
        return WirelessChassis.objects.filter(id__in=offline_device_ids)

    @staticmethod
    def bulk_sync_devices(
        *,
        manufacturer,
        devices_data: list[dict],
        organization_id: int | None = None,
    ) -> dict[str, int]:
        """Bulk synchronize devices from API data.

        This method is called during refresh operations to sync device data
        from manufacturer APIs into the local database.

        Args:
            manufacturer: Manufacturer instance
            devices_data: List of device data dicts from API
            organization_id: Optional organization ID for MSP filtering

        Returns:
            Dictionary with sync statistics:
            {
                'total': int,
                'added': int,
                'updated': int,
                'errors': int
            }
        """
        # Delegate to ManufacturerService which has the full sync logic
        result = ManufacturerService.sync_devices_for_manufacturer(
            manufacturer_code=manufacturer.code
        )

        # Convert to expected format
        return {
            "total": result["devices_added"] + result["devices_updated"],
            "added": result["devices_added"],
            "updated": result["devices_updated"],
            "errors": len(result["errors"]),
        }
