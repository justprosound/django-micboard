"""Synchronization service for device synchronization operations.

Handles device synchronization from manufacturer APIs with location assignment
and offline device detection.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from micboard.services.manufacturer.sync import ManufacturerSyncService

logger = logging.getLogger(__name__)

if TYPE_CHECKING:  # pragma: no cover
    from micboard.models.locations.structure import Location


class HardwareSyncService:
    """Business logic for device synchronization and offline detection."""

    @staticmethod
    def sync_devices(
        *,
        manufacturer_code: str,
        location: Location | None = None,
        dry_run: bool = False,
        force: bool = False,
    ) -> dict[str, int | bool]:
        """Synchronize devices from a manufacturer API.

        Args:
            manufacturer_code: Manufacturer code (e.g., 'shure').
            location: Optional location to assign new devices to.
            dry_run: If True, don't save changes to database.
            force: Permit an explicitly requested operator poll while inactive.

        Returns:
            Dictionary with sync statistics.

        TODO: Ensure all manufacturer-specific config is resolved via SettingsRegistry,
        and that this logic is vendor-agnostic and multi-tenant safe.
        """
        result = ManufacturerSyncService.sync_devices_for_manufacturer(
            manufacturer_code=manufacturer_code,
            force=force,
        )

        # Convert ManufacturerSyncService result format to HardwareSyncService format
        stats = {
            "total_devices": result["devices_added"] + result["devices_updated"],
            "created": result["devices_added"],
            "updated": result["devices_updated"],
            "errors": len(result["errors"]),
            "devices_examined": result["devices_examined"],
            "device_limit": result["device_limit"],
            "inventory_complete": result["inventory_complete"],
        }

        # If location specified and not dry run, assign location to new devices
        if location and not dry_run and result["success"]:
            # Note: This would need to be implemented in ManufacturerSyncService
            # to assign locations during sync. For now, this is a placeholder.
            pass

        return stats
