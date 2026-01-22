"""
Direct device polling service for manually-registered devices.

This service bypasses Shure System API discovery and polls devices directly
using their native protocols (REST API, command strings, etc).
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from micboard.models import Channel, Receiver, Transmitter

logger = logging.getLogger(__name__)


class DirectDevicePollingService:
    """Service for polling devices directly without relying on discovery APIs."""

    def poll_device(self, receiver: Receiver) -> dict[str, Any]:
        """
        Poll a manually-registered device directly.

        Args:
            receiver: Receiver model instance with IP address

        Returns:
            Dictionary with polling results:
                - success: bool
                - data: dict (device data if successful)
                - error: str (error message if failed)
        """
        if not receiver.ip:
            return {"success": False, "error": "Device has no IP address"}

        logger.info("Polling device directly: %s (%s)", receiver.name, receiver.ip)

        # Determine polling method based on device type
        if receiver.device_type in ["ulxd", "ulxd4", "ulxd4d", "ulxd4q"]:
            return self._poll_ulxd_device(receiver)
        elif receiver.device_type in ["slxd", "slxd4", "slxd4d"]:
            return self._poll_slxd_device(receiver)
        elif receiver.device_type in ["qlxd", "qlxd4", "qlxd4d"]:
            return self._poll_qlxd_device(receiver)
        else:
            # Try generic REST API polling
            return self._poll_generic_device(receiver)

    def _poll_ulxd_device(self, receiver: Receiver) -> dict[str, Any]:
        """Poll ULXD device using command strings on port 2202."""
        from micboard.integrations.shure.ulxd_client import ULXDCommandStringClient

        try:
            client = ULXDCommandStringClient(receiver.ip)
            device_data = client.get_device_info()

            if device_data:
                # Update receiver with fresh data
                receiver.firmware_version = device_data.get("firmware", receiver.firmware_version)
                receiver.name = device_data.get("name", receiver.name)
                receiver.is_active = True
                receiver.last_seen = timezone.now()
                receiver.save()

                # Poll channels
                channels_updated = 0
                for channel_num in range(1, device_data.get("channel_count", 4) + 1):
                    channel_data = client.get_channel_info(channel_num)
                    if channel_data:
                        self._update_channel_from_data(receiver, channel_num, channel_data)
                        channels_updated += 1

                return {
                    "success": True,
                    "data": device_data,
                    "channels_updated": channels_updated,
                }
            else:
                return {"success": False, "error": "No data received from device"}

        except Exception as e:
            logger.exception("Error polling ULXD device %s: %s", receiver.ip, e)
            return {"success": False, "error": str(e)}

    def _poll_slxd_device(self, receiver: Receiver) -> dict[str, Any]:
        """Poll SLXD device (placeholder for future implementation)."""
        logger.warning("SLXD direct polling not yet implemented for %s", receiver.ip)
        return {"success": False, "error": "SLXD direct polling not implemented"}

    def _poll_qlxd_device(self, receiver: Receiver) -> dict[str, Any]:
        """Poll QLXD device (placeholder for future implementation)."""
        logger.warning("QLXD direct polling not yet implemented for %s", receiver.ip)
        return {"success": False, "error": "QLXD direct polling not implemented"}

    def _poll_generic_device(self, receiver: Receiver) -> dict[str, Any]:
        """Try generic REST API polling (for conferencing devices with port 443)."""
        logger.warning("Generic device polling not yet implemented for %s", receiver.ip)
        return {"success": False, "error": "Generic polling not implemented"}

    def _update_channel_from_data(
        self, receiver: Receiver, channel_num: int, channel_data: dict[str, Any]
    ) -> None:
        """Update or create channel and transmitter from polled data."""
        channel, _ = Channel.objects.update_or_create(
            receiver=receiver,
            channel_number=channel_num,
        )

        tx_data = channel_data.get("transmitter")
        if tx_data:
            Transmitter.objects.update_or_create(
                channel=channel,
                defaults={
                    "battery": tx_data.get("battery", 255),
                    "battery_charge": tx_data.get("battery_charge"),
                    "audio_level": tx_data.get("audio_level", 0),
                    "rf_level": tx_data.get("rf_level", 0),
                    "frequency": tx_data.get("frequency", ""),
                    "antenna": tx_data.get("antenna", ""),
                    "tx_offset": tx_data.get("tx_offset", 255),
                    "quality": tx_data.get("quality", 255),
                    "runtime": tx_data.get("runtime", ""),
                    "status": tx_data.get("status", ""),
                    "name": tx_data.get("name", ""),
                    "name_raw": tx_data.get("name_raw", ""),
                },
            )

    def poll_all_manual_devices(self) -> dict[str, Any]:
        """
        Poll all manually-registered devices.

        Returns:
            Dictionary with polling results summary
        """
        # Get all receivers that don't have an api_device_id (manual devices)
        manual_receivers = Receiver.objects.filter(api_device_id__isnull=True) | Receiver.objects.filter(
            api_device_id=""
        )

        results = {"total": 0, "success": 0, "failed": 0, "errors": []}

        for receiver in manual_receivers:
            results["total"] += 1
            result = self.poll_device(receiver)

            if result["success"]:
                results["success"] += 1
                logger.info("Successfully polled manual device: %s", receiver.name)
            else:
                results["failed"] += 1
                results["errors"].append(
                    {"device": receiver.name, "ip": receiver.ip, "error": result.get("error")}
                )
                logger.warning(
                    "Failed to poll manual device %s: %s", receiver.name, result.get("error")
                )

        return results
