"""Discovery orchestration service.

Centralizes discovery workflow logic previously in signal handlers.
Supports CIDR scanning, FQDN resolution, and device population.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from micboard.models.discovery import DiscoveredDevice

if TYPE_CHECKING:  # pragma: no cover
    from micboard.models.discovery import Manufacturer

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
        from micboard.models.discovery import Manufacturer
        from micboard.services.sync.hardware_sync_service import HardwareSyncService

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
        from micboard.models.discovery import Manufacturer

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
        """Store discovered devices for UI browsing with manufacturer-aware metadata.

        This method delegates manufacturer-specific extraction to small helpers to
        keep the persistence flow simple and testable.
        """
        from micboard.models.discovery import DiscoveredDevice

        for device_data in devices:
            try:
                ip, device_type, channels = DiscoveryOrchestrationService._extract_common_fields(
                    device_data
                )
                if not ip:
                    logger.debug("Skipping device without IP address: %s", device_data)
                    continue

                if "hardwareIdentity" in device_data or "softwareIdentity" in device_data:
                    model, api_device_id, metadata, generic_status = (
                        DiscoveryOrchestrationService._extract_shure_fields(device_data)
                    )
                else:
                    model, api_device_id, metadata, generic_status = (
                        DiscoveryOrchestrationService._extract_generic_fields(device_data)
                    )

                defaults = {
                    "device_type": device_type,
                    "model": model,
                    "channels": channels,
                    "api_device_id": api_device_id,
                    "status": generic_status,
                    "metadata": metadata,
                    "manufacturer": manufacturer,
                }

                DiscoveredDevice.objects.update_or_create(
                    ip=ip,
                    manufacturer=manufacturer,
                    defaults=defaults,
                )
            except Exception as e:
                logger.debug("Error persisting discovered device: %s", e)

    @staticmethod
    def _extract_common_fields(device_data: dict[str, Any]) -> tuple[str, str, int]:
        ip = (
            device_data.get("ip")
            or device_data.get("ipAddress")
            or device_data.get("communicationProtocol", {}).get("address")
            or ""
        )
        device_type = device_data.get("type", "unknown")
        channels = len(device_data.get("channels", []))
        return ip, device_type, channels

    @staticmethod
    def _extract_shure_fields(device_data: dict[str, Any]) -> tuple[str, str, dict, str]:
        hardware_identity = device_data.get("hardwareIdentity", {})
        software_identity = device_data.get("softwareIdentity", {})
        comm_protocol = device_data.get("communicationProtocol", {})

        model = software_identity.get("model", device_data.get("model", ""))
        api_device_id = hardware_identity.get("deviceId", device_data.get("id", ""))

        metadata = {
            "compatibility": device_data.get("compatibility", "UNKNOWN"),
            "deviceState": device_data.get("deviceState", "UNKNOWN"),
            "hardwareIdentity": hardware_identity,
            "softwareIdentity": software_identity,
            "communicationProtocol": comm_protocol,
        }

        device_state = device_data.get("deviceState", "UNKNOWN")
        compatibility = device_data.get("compatibility", "UNKNOWN")

        if compatibility in {"INCOMPATIBLE_TOO_OLD", "INCOMPATIBLE_TOO_NEW"}:
            generic_status = DiscoveredDevice.STATUS_INCOMPATIBLE
        elif device_state == "ONLINE":
            generic_status = DiscoveredDevice.STATUS_READY
        elif device_state == "DISCOVERED":
            generic_status = DiscoveredDevice.STATUS_PENDING
        elif device_state == "ERROR":
            generic_status = DiscoveredDevice.STATUS_ERROR
        elif device_state == "OFFLINE":
            generic_status = DiscoveredDevice.STATUS_OFFLINE
        else:
            generic_status = DiscoveredDevice.STATUS_UNKNOWN

        return model, api_device_id, metadata, generic_status

    @staticmethod
    def _extract_generic_fields(device_data: dict[str, Any]) -> tuple[str, str, dict, str]:
        model = device_data.get("model", device_data.get("deviceModel", ""))
        api_device_id = device_data.get("id", device_data.get("deviceId", ""))

        metadata = {
            k: v
            for k, v in device_data.items()
            if k
            not in {
                "ip",
                "ipAddress",
                "type",
                "channels",
                "model",
                "deviceModel",
                "id",
                "deviceId",
            }
        }

        device_status = device_data.get("status", "")
        if device_status in {"online", "ready", "active"}:
            generic_status = DiscoveredDevice.STATUS_READY
        elif device_status in {"offline", "inactive"}:
            generic_status = DiscoveredDevice.STATUS_OFFLINE
        elif device_status in {"error", "fault"}:
            generic_status = DiscoveredDevice.STATUS_ERROR
        else:
            generic_status = DiscoveredDevice.STATUS_PENDING

        return model, api_device_id, metadata, generic_status

    @staticmethod
    def _emit_refresh_broadcast(
        manufacturer: Manufacturer,
        devices_data: list[dict[str, Any]],
        organization_id: int | None = None,
    ) -> None:
        """Broadcast refresh update (replacing signals)."""
        try:
            from channels.layers import get_channel_layer

            if get_channel_layer():
                from micboard.services.notification.broadcast_service import BroadcastService

                BroadcastService.broadcast_device_update(
                    manufacturer=manufacturer,
                    data={
                        "device_count": len(devices_data),
                        "organization_id": organization_id,
                    },
                )
        except Exception as e:
            logger.debug("Failed to broadcast refresh update: %s", e)
