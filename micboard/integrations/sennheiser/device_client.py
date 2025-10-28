from __future__ import annotations

import logging
from typing import Any, Optional, cast

from micboard.manufacturers.base import BaseAPIClient

from .exceptions import SennheiserAPIError
from .rate_limiter import rate_limit
from .transformers import SennheiserDataTransformer

logger = logging.getLogger(__name__)


class SennheiserDeviceClient:
    """Client for interacting with Sennheiser SSCv2 API for device data."""

    def __init__(self, api_client: BaseAPIClient):
        self.api_client = api_client
        self.transformer = SennheiserDataTransformer()

    @rate_limit(calls_per_second=5.0)
    def get_devices(self) -> list[dict[str, Any]]:
        """Get list of all devices from Sennheiser SSCv2 API."""
        # Placeholder endpoint - needs to be verified from OpenAPI specs
        result = self.api_client._make_request("GET", "/api/devices")
        return result if isinstance(result, list) else []

    @rate_limit(calls_per_second=5.0)
    def get_supported_device_models(self) -> list[str]:
        """Fetch the list of supported device models from Sennheiser SSCv2 API."""
        try:
            # Placeholder endpoint
            result = self.api_client._make_request("GET", "/api/devices/models")
            return result if isinstance(result, list) else []
        except SennheiserAPIError:
            logger.debug("Supported device models endpoint not available or failed")
            return []

    @rate_limit(calls_per_second=10.0)
    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Get detailed data for a specific device."""
        return cast(
            Optional[dict[str, Any]],
            self.api_client._make_request("GET", f"/api/devices/{device_id}"),
        )

    @rate_limit(calls_per_second=10.0)
    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        """Get channel data for a device."""
        result = self.api_client._make_request("GET", f"/api/devices/{device_id}/channels")
        return result if isinstance(result, list) else []

    @rate_limit(calls_per_second=10.0)
    def get_transmitter_data(self, device_id: str, channel: int) -> dict[str, Any] | None:
        """Get transmitter data for a specific channel."""
        return cast(
            Optional[dict[str, Any]],
            self.api_client._make_request(
                "GET", f"/api/devices/{device_id}/channels/{channel}/tx"
            ),
        )

    def get_device_identity(self, device_id: str) -> dict[str, Any] | None:
        """Fetch device identity info from Sennheiser API."""
        try:
            return cast(
                Optional[dict[str, Any]],
                self.api_client._make_request("GET", f"/api/devices/{device_id}/identify"),
            )
        except SennheiserAPIError:
            logger.debug("Identity endpoint not available for device %s", device_id)
            return None

    def get_device_network(self, device_id: str) -> dict[str, Any] | None:
        """Fetch device network info (hostname, MAC) if available."""
        try:
            return cast(
                Optional[dict[str, Any]],
                self.api_client._make_request("GET", f"/api/devices/{device_id}/network"),
            )
        except SennheiserAPIError:
            logger.debug("Network endpoint not available for device %s", device_id)
            return None

    def get_device_status(self, device_id: str) -> dict[str, Any] | None:
        """Fetch general device status details if available."""
        try:
            return cast(
                Optional[dict[str, Any]],
                self.api_client._make_request("GET", f"/api/devices/{device_id}/status"),
            )
        except SennheiserAPIError:
            logger.debug("Status endpoint not available for device %s", device_id)
            return None

    def _enrich_device_data(self, device_id: str, device_data: dict[str, Any]) -> dict[str, Any]:
        """Best-effort enrichment of device data from optional endpoints."""
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
            logger.info("Polling %d devices from Sennheiser SSCv2 API", len(devices))
        except SennheiserAPIError:
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

                try:
                    device_data = self._enrich_device_data(device_id, device_data)
                except Exception:
                    logger.debug("Enrichment failed for device %s", device_id)

                channels = self.get_device_channels(device_id)
                device_data["channels"] = channels

                transformed = self.transformer.transform_device_data(device_data)
                if transformed:
                    data[device_id] = transformed
                else:
                    logger.warning("Failed to transform data for device %s", device_id)
            except SennheiserAPIError:
                logger.exception("Error polling device %s", device_id)
                continue

        missing_fw = [d for d in data.values() if not d.get("firmware")]
        if missing_fw:
            logger.warning("%d devices missing firmware info", len(missing_fw))
        else:
            logger.info("Firmware info present for all devices")

        logger.info("Successfully polled %d devices", len(data))
        return data