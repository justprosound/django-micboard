"""Direct device polling service for manually-registered devices.

This service bypasses Shure System API discovery and polls devices directly
using their native protocols (REST API, command strings, etc).
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from micboard.models import RFChannel, WirelessChassis, WirelessUnit

logger = logging.getLogger(__name__)


class DirectDevicePollingService:
    """Service for polling devices directly without relying on discovery APIs."""

    def poll_device(self, chassis: WirelessChassis) -> dict[str, Any]:
        """Poll a manually-registered device directly.

        Args:
            chassis: WirelessChassis model instance with IP address

        Returns:
            Dictionary with polling results:
                - success: bool
                - data: dict (device data if successful)
                - error: str (error message if failed)
        """
        if not chassis.ip:
            return {"success": False, "error": "Device has no IP address"}

        logger.info("Polling device directly: %s (%s)", chassis.name, chassis.ip)

        # Determine polling method based on device model
        model_upper = chassis.model.upper()
        if any(m in model_upper for m in ["ULXD", "ULX-D"]):
            return self._poll_ulxd_device(chassis)
        elif any(m in model_upper for m in ["SLXD", "SLX-D"]):
            return self._poll_slxd_device(chassis)
        elif "QLXD" in model_upper:
            return self._poll_qlxd_device(chassis)
        else:
            # Try generic REST API polling
            return self._poll_generic_device(chassis)

    def _poll_ulxd_device(self, chassis: WirelessChassis) -> dict[str, Any]:
        """Poll ULXD device using command strings on port 2202."""
        from micboard.integrations.shure.ulxd_client import ULXDCommandStringClient

        try:
            client = ULXDCommandStringClient(chassis.ip)
            device_data = client.get_device_info()

            if device_data:
                # Update chassis with fresh data
                chassis.firmware_version = device_data.get("firmware", chassis.firmware_version)
                chassis.name = device_data.get("name", chassis.name)
                chassis.is_online = True
                chassis.status = "online"
                chassis.last_seen = timezone.now()
                chassis.save()

                # Poll channels
                channels_updated = 0
                for channel_num in range(1, device_data.get("channel_count", 4) + 1):
                    channel_data = client.get_channel_info(channel_num)
                    if channel_data:
                        self._update_channel_from_data(chassis, channel_num, channel_data)
                        channels_updated += 1

                return {
                    "success": True,
                    "data": device_data,
                    "channels_updated": channels_updated,
                }
            else:
                return {"success": False, "error": "No data received from device"}

        except Exception as e:
            logger.exception("Error polling ULXD device %s: %s", chassis.ip, e)
            return {"success": False, "error": str(e)}

    def _poll_slxd_device(self, chassis: WirelessChassis) -> dict[str, Any]:
        """Poll SLXD device (placeholder for future implementation)."""
        logger.warning("SLXD direct polling not yet implemented for %s", chassis.ip)
        return {"success": False, "error": "SLXD direct polling not implemented"}

    def _poll_qlxd_device(self, chassis: WirelessChassis) -> dict[str, Any]:
        """Poll QLXD device (placeholder for future implementation)."""
        logger.warning("QLXD direct polling not yet implemented for %s", chassis.ip)
        return {"success": False, "error": "QLXD direct polling not implemented"}

    def _poll_generic_device(self, chassis: WirelessChassis) -> dict[str, Any]:
        """Try generic REST API polling (for conferencing devices with port 443)."""
        logger.warning("Generic device polling not yet implemented for %s", chassis.ip)
        return {"success": False, "error": "Generic polling not implemented"}

    def _update_channel_from_data(
        self, chassis: WirelessChassis, channel_num: int, channel_data: dict[str, Any]
    ) -> None:
        """Update or create channel and unit from polled data."""
        channel, _ = RFChannel.objects.update_or_create(
            chassis=chassis,
            channel_number=channel_num,
        )

        unit_data = channel_data.get("transmitter")
        if unit_data:
            unit, _ = WirelessUnit.objects.update_or_create(
                base_chassis=chassis,
                slot=channel_num,  # Assuming slot matches channel for direct polling legacy
                defaults={
                    "manufacturer": chassis.manufacturer,
                    "device_type": "mic_transmitter",
                    "battery": unit_data.get("battery", 255),
                    "battery_charge": unit_data.get("battery_charge"),
                    "audio_level": unit_data.get("audio_level", 0),
                    "rf_level": unit_data.get("rf_level", 0),
                    "frequency": unit_data.get("frequency", ""),
                    "antenna": unit_data.get("antenna", ""),
                    "tx_offset": unit_data.get("tx_offset", 255),
                    "quality": unit_data.get("quality", 255),
                    "status": "online",
                    "name": unit_data.get("name", ""),
                    "assigned_resource": channel,
                },
            )

            # Link back
            if channel.active_wireless_unit != unit:
                channel.active_wireless_unit = unit
                channel.save(update_fields=["active_wireless_unit"])

    def poll_all_manual_devices(self) -> dict[str, Any]:
        """Poll all manually-registered devices.

        Returns:
            Dictionary with polling results summary
        """
        # Get all chassis that don't have an api_device_id (manual devices)
        manual_chassis = WirelessChassis.objects.filter(
            api_device_id__isnull=True
        ) | WirelessChassis.objects.filter(api_device_id="")

        results = {"total": 0, "success": 0, "failed": 0, "errors": []}

        for chassis in manual_chassis:
            results["total"] += 1
            result = self.poll_device(chassis)

            if result["success"]:
                results["success"] += 1
                logger.info("Successfully polled manual device: %s", chassis.name)
            else:
                results["failed"] += 1
                results["errors"].append(
                    {"device": chassis.name, "ip": chassis.ip, "error": result.get("error")}
                )
                logger.warning(
                    "Failed to poll manual device %s: %s", chassis.name, result.get("error")
                )

        return results
