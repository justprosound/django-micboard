from __future__ import annotations

import logging
from typing import Any, cast

from micboard.services.common.base.client import BaseAPIClient
from micboard.services.common.base.rate_limiter import rate_limit

from .exceptions import SennheiserAPIError

logger = logging.getLogger(__name__)


class SennheiserDeviceClient:
    """Client for interacting with Sennheiser SSCv2 API for device data."""

    def __init__(self, api_client: BaseAPIClient):
        """Create device client using the provided API client."""
        self.api_client = api_client

    def get_devices(self) -> list[dict[str, Any]]:
        """Get list of all devices from Sennheiser SSCv2 API."""
        result = self.api_client._make_request("GET", "/api/devices")
        return cast(list[dict[str, Any]], result) if result is not None else []

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
            dict[str, Any] | None,
            self.api_client._make_request("GET", f"/api/devices/{device_id}"),
        )

    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        """Get channel data for a device."""
        result = self.api_client._make_request("GET", f"/api/devices/{device_id}/channels")
        return cast(list[dict[str, Any]], result) if result is not None else []
