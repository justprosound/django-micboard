"""
Shure manufacturer plugin for django-micboard.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Union, cast

from micboard.manufacturers import ManufacturerPlugin

from .client import ShureSystemAPIClient
from .transformers import ShureDataTransformer

logger = logging.getLogger(__name__)


class ShurePlugin(ManufacturerPlugin):
    """Plugin for Shure wireless microphone systems."""

    @property
    def name(self) -> str:
        return "Shure"

    @property
    def code(self) -> str:
        return "shure"

    def __init__(self, manufacturer: Any):
        super().__init__(manufacturer)
        self.client = ShureSystemAPIClient()
        self.transformer = ShureDataTransformer()

    def get_devices(self) -> list[dict[str, Any]]:
        """Get list of all devices from Shure System API."""
        return cast(list[dict[str, Any]], self.client.get_devices())

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Get detailed data for a specific device."""
        return cast(Union[dict[str, Any], None], self.client.get_device(device_id))

    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        """Get channel data for a device."""
        return cast(list[dict[str, Any]], self.client.get_device_channels(device_id))

    def transform_device_data(self, api_data: dict[str, Any]) -> dict[str, Any] | None:
        """Transform Shure API data to micboard format."""
        return self.transformer.transform_device_data(api_data)

    def transform_transmitter_data(
        self, tx_data: dict[str, Any], channel_num: int
    ) -> dict[str, Any] | None:
        """Transform transmitter data from Shure format to micboard format."""
        return self.transformer.transform_transmitter_data(tx_data, channel_num)

    def get_device_identity(self, device_id: str) -> dict[str, Any] | None:
        """Fetch device identity info from Shure API."""
        return self.client.get_device_identity(device_id)

    def get_device_network(self, device_id: str) -> dict[str, Any] | None:
        """Fetch device network info from Shure API."""
        return self.client.get_device_network(device_id)

    def get_device_status(self, device_id: str) -> dict[str, Any] | None:
        """Fetch device status info from Shure API."""
        return self.client.get_device_status(device_id)

    def connect_and_subscribe(
        self, device_id: str, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """Establish WebSocket connection and subscribe to Shure device updates."""
        # WebSocket support not yet implemented for Shure plugin
        raise NotImplementedError("WebSocket support not yet implemented for Shure manufacturer")

    def is_healthy(self) -> bool:
        """Check if the Shure API client is healthy."""
        return self.client.is_healthy()

    def check_health(self) -> dict[str, Any]:
        """Perform health check against Shure API."""
        return self.client.check_health()
