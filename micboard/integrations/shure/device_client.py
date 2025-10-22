from __future__ import annotations

import logging
from typing import Any

from micboard.manufacturers.base import BaseAPIClient

from .exceptions import ShureAPIError
from .rate_limiter import rate_limit
from .transformers import ShureDataTransformer

logger = logging.getLogger(__name__)


class ShureDeviceClient:
    """Client for interacting with Shure System API for device data."""

    def __init__(self, api_client: BaseAPIClient):
        self.api_client = api_client
        self.transformer = ShureDataTransformer()

    @rate_limit(calls_per_second=5.0)
    def get_devices(self) -> list[dict[str, Any]]:
        """Get list of all devices from Shure System API."""
        result = self.api_client._make_request("GET", "/api/v1/devices")
        return result if isinstance(result, list) else []

    @rate_limit(calls_per_second=5.0)
    def get_supported_device_models(self) -> list[str]:
        """Fetch the list of supported device models from Shure System API.

        Returns:
            A list of model identifiers (strings). If the endpoint is not
            available or fails, an empty list is returned.
        """
        try:
            result = self.api_client._make_request("GET", "/api/v1/devices/models")
            return result if isinstance(result, list) else []
        except ShureAPIError:
            logger.debug("Supported device models endpoint not available or failed")
            return []

    @rate_limit(calls_per_second=10.0)
    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Get detailed data for a specific device."""
        return self.api_client._make_request("GET", f"/api/v1/devices/{device_id}")

    @rate_limit(calls_per_second=10.0)
    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        """Get channel data for a device."""
        result = self.api_client._make_request("GET", f"/api/v1/devices/{device_id}/channels")
        return result if isinstance(result, list) else []

    @rate_limit(calls_per_second=10.0)
    def get_transmitter_data(self, device_id: str, channel: int) -> dict[str, Any] | None:
        """Get transmitter data for a specific channel."""
        return self.api_client._make_request(
            "GET", f"/api/v1/devices/{device_id}/channels/{channel}/tx"
        )

    def get_device_identity(self, device_id: str) -> dict[str, Any] | None:
        """Fetch device identity info from Shure API."""
        try:
            return self.api_client._make_request("GET", f"/api/v1/devices/{device_id}/identify")
        except ShureAPIError:
            logger.debug("Identity endpoint not available for device %s", device_id)
            return None

    def get_device_network(self, device_id: str) -> dict[str, Any] | None:
        """Fetch device network info (hostname, MAC) if available."""
        try:
            return self.api_client._make_request("GET", f"/api/v1/devices/{device_id}/network")
        except ShureAPIError:
            logger.debug("Network endpoint not available for device %s", device_id)
            return None

    def get_device_status(self, device_id: str) -> dict[str, Any] | None:
        """Fetch general device status details if available."""
        try:
            return self.api_client._make_request("GET", f"/api/v1/devices/{device_id}/status")
        except ShureAPIError:
            logger.debug("Status endpoint not available for device %s", device_id)
            return None

    def _enrich_device_data(self, device_id: str, device_data: dict[str, Any]) -> dict[str, Any]:
        """Best-effort enrichment of device data from optional endpoints.

        Merges fields like serial number, hostname, MAC, model variant, band, and location
        when available.

        Args:
            device_id: Device ID
            device_data: Base device data to enrich

        Returns:
            Enriched device data
        """
        identity = self.get_device_identity(device_id)
        if identity and isinstance(identity, dict):
            device_data.setdefault("serial_number", identity.get("serialNumber"))
            device_data.setdefault("model_variant", identity.get("modelVariant"))
            fw = identity.get("firmwareVersion")
            if fw:
                device_data["firmware_version"] = fw

        net = self.get_device_network(device_id)
        if net and isinstance(net, dict):
            device_data.setdefault("hostname", net.get("hostname"))
            device_data.setdefault("mac_address", net.get("macAddress"))

        status = self.get_device_status(device_id)
        if status and isinstance(status, dict):
            device_data.setdefault("frequency_band", status.get("frequencyBand"))
            device_data.setdefault("location", status.get("location"))

        return device_data

    def poll_all_devices(self) -> dict[str, dict[str, Any]]:
        """Poll all devices and return aggregated data with transmitter info."""
        try:
            devices = self.get_devices()
            logger.info("Polling %d devices from Shure System API", len(devices))
        except ShureAPIError:
            logger.exception("Failed to get device list")
            return {}

        data: dict[str, dict[str, Any]] = {}
        for device in devices:
            device_id = device.get("id")
            if not device_id:
                logger.warning("Device missing 'id' field: %s", device)
                continue

            try:
                device_data = self.get_device(device_id)
                if not device_data:
                    logger.warning("No data returned for device %s", device_id)
                    continue

                # Optional enrichment from additional endpoints (best-effort)
                try:
                    device_data = self._enrich_device_data(device_id, device_data)
                except Exception:
                    logger.debug("Enrichment failed for device %s", device_id)

                # Get channel/transmitter data
                channels = self.get_device_channels(device_id)
                device_data["channels"] = channels

                # Transform to micboard format
                transformed = self.transformer.transform_device_data(device_data)
                if transformed:
                    data[device_id] = transformed
                else:
                    logger.warning("Failed to transform data for device %s", device_id)
            except ShureAPIError:
                logger.exception("Error polling device %s", device_id)
                continue

        # Firmware coverage validation
        missing_fw = [d for d in data.values() if not d.get("firmware")]
        if missing_fw:
            logger.warning("%d devices missing firmware info", len(missing_fw))
        else:
            logger.info("Firmware info present for all devices")

        logger.info("Successfully polled %d devices", len(data))
        return data
