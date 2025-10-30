"""
Sennheiser manufacturer plugin for django-micboard.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, cast

from micboard.manufacturers import ManufacturerPlugin

logger = logging.getLogger(__name__)


class SennheiserPlugin(ManufacturerPlugin):
    """Plugin for Sennheiser wireless microphone systems."""

    @property
    def name(self) -> str:
        return "Sennheiser"

    @property
    def code(self) -> str:
        return "sennheiser"

    def __init__(self, manufacturer: Any):
        super().__init__(manufacturer)
        from .client import SennheiserSystemAPIClient

        self.client: SennheiserSystemAPIClient = SennheiserSystemAPIClient()
        from .transformers import SennheiserDataTransformer

        self.transformer = SennheiserDataTransformer()

    def get_devices(self) -> list[dict[str, Any]]:
        """Get list of all devices from Sennheiser SSCv2 API."""
        return self.client.devices.get_devices()

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Get detailed data for a specific device."""
        return cast(Optional[dict[str, Any]], self.client.devices.get_device(device_id))

    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        """Get channel data for a device."""
        return self.client.devices.get_device_channels(device_id)

    def transform_device_data(self, api_data: dict[str, Any]) -> dict[str, Any] | None:
        """Transform Sennheiser SSCv2 API data to micboard format."""
        return self.transformer.transform_device_data(api_data)

    def transform_transmitter_data(
        self, tx_data: dict[str, Any], channel_num: int
    ) -> dict[str, Any] | None:
        """Transform transmitter data from Sennheiser format to micboard format."""
        return self.transformer.transform_transmitter_data(tx_data, channel_num)

    def connect_and_subscribe(
        self, device_id: str, callback: Callable[[dict[str, Any]], None]
    ) -> None:
        """Establish SSE connection and subscribe to Sennheiser device updates."""
        from asgiref.sync import async_to_sync

        from .sse_client import connect_and_subscribe

        async_to_sync(connect_and_subscribe)(self.client, device_id, callback)

    def is_healthy(self) -> bool:
        """Check if the Sennheiser SSCv2 API client is healthy."""
        return self.client.is_healthy()

    def check_health(self) -> dict[str, Any]:
        """Perform health check against Sennheiser SSCv2 API."""
        return self.client.check_health()
