"""Discovery orchestration service.

Centralizes discovery workflow logic previously in signal handlers.
Supports CIDR scanning, FQDN resolution, and device population.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from micboard.models import Manufacturer

logger = logging.getLogger(__name__)


class DiscoveryOrchestrationService:
    """Orchestrates device discovery across manufacturer plugins.

    Handles:
    - Discovery request processing (formerly in request_signals)
    - CIDR/FQDN configuration updates (formerly discovery_signals)
    - Result aggregation and broadcast

    All heavy lifting delegated to DiscoveryService.
    """

    @staticmethod
    def handle_discovery_requested(
        *,
        manufacturer_code: str | None = None,
        organization_id: int | None = None,
        campus_id: int | None = None,
    ) -> dict[str, Any]:
        """Process discovery request for manufacturer(s).

        Args:
            manufacturer_code: Optional specific manufacturer
            organization_id: Optional org filter
            campus_id: Optional campus filter

        Returns:
            Mapping: {manufacturer_code: {status, count, devices/error}}
        """
        from micboard.manufacturers import get_manufacturer_plugin
        from micboard.models import Manufacturer

        results: dict[str, Any] = {}

        try:
            if manufacturer_code:
                manufacturers = Manufacturer.objects.filter(code=manufacturer_code)
            else:
                manufacturers = Manufacturer.objects.all()

            for mfg in manufacturers:
                try:
                    plugin_cls = get_manufacturer_plugin(mfg.code)
                    plugin = plugin_cls(mfg)

                    devices = plugin.get_devices() or []

                    # Store discovered devices for UI
                    DiscoveryOrchestrationService._persist_discovered_devices(
                        devices, mfg, organization_id, campus_id
                    )

                    results[mfg.code] = {
                        "status": "success",
                        "count": len(devices),
                        "devices": devices,
                    }

                except Exception as e:
                    logger.exception("Discovery error for %s: %s", mfg.code, e)
                    results[mfg.code] = {"status": "error", "error": str(e)}

        except Exception as e:
            logger.exception("Unhandled error in discovery: %s", e)
            return {"error": {"status": "error", "error": str(e)}}

        return results

    @staticmethod
    def handle_refresh_requested(
        *,
        manufacturer_code: str | None = None,
        organization_id: int | None = None,
        campus_id: int | None = None,
    ) -> dict[str, Any]:
        """Process refresh request to update device details.

        Args:
            manufacturer_code: Optional specific manufacturer
            organization_id: Optional org filter
            campus_id: Optional campus filter

        Returns:
            Mapping: {manufacturer_code: {status, device_count, updated}}
        """
        from micboard.manufacturers import get_manufacturer_plugin
        from micboard.models import Manufacturer
        from micboard.services.hardware_sync_service import HardwareSyncService

        results: dict[str, Any] = {}

        try:
            if manufacturer_code:
                manufacturers = Manufacturer.objects.filter(code=manufacturer_code)
            else:
                manufacturers = Manufacturer.objects.all()

            for mfg in manufacturers:
                try:
                    plugin_cls = get_manufacturer_plugin(mfg.code)
                    plugin = plugin_cls(mfg)

                    devices_data = plugin.get_devices() or []

                    # Bulk sync devices
                    stats = HardwareSyncService.bulk_sync_devices(
                        manufacturer=mfg,
                        devices_data=devices_data,
                        organization_id=organization_id,
                    )

                    # Emit broadcast signal (minimal)
                    DiscoveryOrchestrationService._emit_refresh_broadcast(
                        mfg, devices_data, organization_id
                    )

                    results[mfg.code] = {
                        "status": "success",
                        "device_count": len(devices_data),
                        "updated": stats["updated"],
                        "added": stats["added"],
                    }

                except Exception as e:
                    logger.exception("Refresh error for %s: %s", mfg.code, e)
                    results[mfg.code] = {"status": "error", "error": str(e)}

        except Exception as e:
            logger.exception("Unhandled error in refresh: %s", e)
            return {"error": {"status": "error", "error": str(e)}}

        return results

    @staticmethod
    def handle_device_detail_requested(
        *,
        manufacturer_code: str | None = None,
        device_id: str | None = None,
        organization_id: int | None = None,
    ) -> dict[str, Any]:
        """Fetch detailed data for a single device.

        Args:
            manufacturer_code: Optional specific manufacturer
            device_id: Device ID to fetch
            organization_id: Optional org filter

        Returns:
            {manufacturer_code: {status, device}} or {error: msg}
        """
        from micboard.manufacturers import get_manufacturer_plugin
        from micboard.models import Manufacturer

        if not device_id:
            return {"status": "error", "error": "device_id required"}

        try:
            if manufacturer_code:
                manufacturers = Manufacturer.objects.filter(code=manufacturer_code)
            else:
                manufacturers = Manufacturer.objects.all()

            for mfg in manufacturers:
                try:
                    plugin_cls = get_manufacturer_plugin(mfg.code)
                    plugin = plugin_cls(mfg)

                    device = plugin.get_device(device_id)
                    if not device:
                        continue

                    # Enrich with channels
                    try:
                        channels = plugin.get_device_channels(device_id)
                        device["channels"] = channels
                    except Exception:
                        logger.debug("No channel data for %s", device_id)

                    return {mfg.code: {"status": "success", "device": device}}

                except Exception as e:
                    logger.exception("Error fetching device %s for %s: %s", device_id, mfg.code, e)
                    return {mfg.code: {"status": "error", "error": str(e)}}

            return {"status": "error", "error": "device not found"}

        except Exception as e:
            logger.exception("Unhandled error fetching device detail: %s", e)
            return {"status": "error", "error": "unhandled error"}

    # Private methods

    @staticmethod
    def _persist_discovered_devices(
        devices: list[dict[str, Any]],
        manufacturer: Manufacturer,
        organization_id: int | None = None,
        campus_id: int | None = None,
    ) -> None:
        """Store discovered devices for UI browsing."""
        from micboard.models import DiscoveredDevice

        for device_data in devices:
            try:
                DiscoveredDevice.objects.update_or_create(
                    ip=device_data.get("ip", ""),
                    manufacturer=manufacturer,
                    defaults={
                        "device_type": device_data.get("type", "unknown"),
                        "channels": len(device_data.get("channels", [])),
                        "organization_id": organization_id,
                        "campus_id": campus_id,
                    },
                )
            except Exception as e:
                logger.debug("Error persisting discovered device: %s", e)

    @staticmethod
    def _emit_refresh_broadcast(
        manufacturer: Manufacturer,
        devices_data: list[dict[str, Any]],
        organization_id: int | None = None,
    ) -> None:
        """Broadcast refresh update (replacing signals)."""
        try:
            from micboard.services.broadcast_service import BroadcastService

            BroadcastService.broadcast_device_update(
                manufacturer=manufacturer,
                data={
                    "device_count": len(devices_data),
                    "organization_id": organization_id,
                },
            )
        except Exception as e:
            logger.debug("Failed to broadcast refresh update: %s", e)
