"""Shure manufacturer plugin for django-micboard."""

from __future__ import annotations

import logging
from typing import Any, Callable, cast

from micboard.manufacturers.base import BasePlugin

from .client import ShureSystemAPIClient
from .transformers import ShureDataTransformer

logger = logging.getLogger(__name__)


class ShurePlugin(BasePlugin):
    """Plugin for Shure wireless microphone systems."""

    @property
    def name(self) -> str:
        return "Shure"

    @property
    def code(self) -> str:
        return "shure"

    def __init__(self, manufacturer: Any):
        super().__init__(manufacturer)
        self.transformer = ShureDataTransformer()
        self._client = None  # type: ShureSystemAPIClient | None

    def get_client(self) -> ShureSystemAPIClient:
        """Return an instance of the ShureSystemAPIClient for this manufacturer."""
        if self._client is None:
            self._client = ShureSystemAPIClient()
        return self._client

    def get_devices(self) -> list[dict[str, Any]]:
        """Get list of all devices from Shure System API."""
        return cast(list[dict[str, Any]], self.get_client().devices.get_devices())

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
        return self.get_client().devices.get_device_identity(device_id)

    def get_device_network(self, device_id: str) -> dict[str, Any] | None:
        """Fetch device network info from Shure API."""
        return self.get_client().devices.get_device_network(device_id)

    def get_device_status(self, device_id: str) -> dict[str, Any] | None:
        """Fetch device status info from Shure API."""
        return self.get_client().devices.get_device_status(device_id)

    async def connect_and_subscribe(
        self, device_id: str, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """Establish WebSocket connection and subscribe to Shure device updates."""
        from .websocket import connect_and_subscribe as ws_connect_and_subscribe

        await ws_connect_and_subscribe(self.get_client(), device_id, callback)

    def is_healthy(self) -> bool:
        """Check if the Shure API client is healthy."""
        return self.get_client().is_healthy()

    def check_health(self) -> dict[str, Any]:
        """Perform health check against Shure API."""
        return self.get_client().check_health()

    def add_discovery_ips(self, ips: list[str]) -> bool:
        """Add IP addresses to the Shure System API manual discovery list."""
        return cast(bool, self.get_client().discovery.add_discovery_ips(ips))

    def get_discovery_ips(self) -> list[str]:
        """Retrieve the current manual discovery IPs from Shure System API."""
        return cast(list[str], self.get_client().discovery.get_discovery_ips())

    def remove_discovery_ips(self, ips: list[str]) -> bool:
        """Remove IP addresses from the Shure System API manual discovery list."""
        return cast(bool, self.get_client().discovery.remove_discovery_ips(ips))
