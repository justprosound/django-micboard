"""Sennheiser manufacturer plugin for django-micboard."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from micboard.services.common.base.plugin import ManufacturerPlugin, RealtimeTransport

if TYPE_CHECKING:
    from micboard.models.discovery.manufacturer import Manufacturer
    from micboard.models.hardware.wireless_chassis import WirelessChassis
    from micboard.services.core.hardware import NormalizedChannel, NormalizedChassis

from .client import SennheiserSystemAPIClient
from .normalizer import SENNHEISER_NORMALIZER

logger = logging.getLogger(__name__)


class SennheiserPlugin(ManufacturerPlugin):
    """Plugin for Sennheiser wireless microphone systems."""

    @property
    def name(self) -> str:
        return "Sennheiser"

    @property
    def code(self) -> str:
        return "sennheiser"

    def __init__(self, manufacturer: Manufacturer | None) -> None:
        """Initialize Sennheiser plugin and its client."""
        super().__init__(manufacturer)
        self.client: SennheiserSystemAPIClient = SennheiserSystemAPIClient()

    def get_devices(self) -> list[dict[str, Any]]:
        """Get list of all devices from Sennheiser SSCv2 API."""
        return self.client.devices.get_devices()

    def get_client(self) -> SennheiserSystemAPIClient:
        """Return the configured Sennheiser system client."""
        return self.client

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Get detailed data for a specific device."""
        return self.client.devices.get_device(device_id)

    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        """Get channel data for a device."""
        return self.client.devices.get_device_channels(device_id)

    def normalize_device(self, api_data: dict[str, Any]) -> NormalizedChassis | None:
        """Normalize one Sennheiser SSCv2 device payload."""
        return SENNHEISER_NORMALIZER.normalize_device(api_data)

    def normalize_channels(self, api_channels: list[dict[str, Any]]) -> list[NormalizedChannel]:
        """Normalize a Sennheiser SSCv2 channel list."""
        return SENNHEISER_NORMALIZER.normalize_channels(api_channels)

    @property
    def realtime_transport(self) -> RealtimeTransport:
        """Sennheiser SSCv2 streams over the SSE subscription its system client opens."""
        return "sse"

    async def subscribe_to_chassis(
        self,
        chassis: WirelessChassis,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Subscribe to one device through the manufacturer-level SSCv2 client."""
        await self.client.connect_and_subscribe(chassis.api_device_id, callback)

    def is_healthy(self) -> bool:
        """Check if the Sennheiser SSCv2 API client is healthy."""
        return self.client.is_healthy()

    def check_health(self) -> dict[str, Any]:
        """Perform health check against Sennheiser SSCv2 API."""
        return self.client.check_health()

    def add_discovery_ips(self, ips: list[str]) -> bool:
        """Add IP addresses to the Sennheiser SSCv2 API manual discovery list."""
        return self.client.discovery.add_discovery_ips(ips)

    def get_discovery_ips(self) -> list[str]:
        """Retrieve the current manual discovery IPs from Sennheiser SSCv2 API."""
        return self.client.discovery.get_discovery_ips()

    def remove_discovery_ips(self, ips: list[str]) -> bool:
        """Remove IP addresses from the Sennheiser SSCv2 API manual discovery list."""
        return self.client.discovery.remove_discovery_ips(ips)
