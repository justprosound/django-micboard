"""Shure manufacturer plugin for django-micboard."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from asgiref.sync import sync_to_async

from micboard.services.common.base.plugin import ManufacturerPlugin, RealtimeTransport
from micboard.services.common.base.utils import build_device_https_url

if TYPE_CHECKING:
    from micboard.models.discovery.manufacturer import Manufacturer
    from micboard.models.hardware.wireless_chassis import WirelessChassis
    from micboard.services.core.hardware import NormalizedChannel, NormalizedChassis

from .client import ShureSystemAPIClient
from .normalizer import SHURE_NORMALIZER

logger = logging.getLogger(__name__)


class ShurePlugin(ManufacturerPlugin):
    """Plugin for Shure wireless microphone systems."""

    @property
    def name(self) -> str:
        return "Shure"

    @property
    def code(self) -> str:
        return "shure"

    def __init__(self, manufacturer: Manufacturer | None) -> None:
        """Initialize Shure plugin and its lazy client."""
        super().__init__(manufacturer)
        self._client = None  # type: ShureSystemAPIClient | None

    def get_client(self) -> ShureSystemAPIClient:
        """Return an instance of the ShureSystemAPIClient for this manufacturer."""
        if self._client is None:
            self._client = ShureSystemAPIClient()
        return self._client

    def get_devices(self) -> list[dict[str, Any]]:
        """Get list of all devices from Shure System API."""
        return self.get_client().devices.get_devices()

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Get detailed data for a specific device."""
        return self.get_client().devices.get_device(device_id)

    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        """Get channel data for a device."""
        return self.get_client().devices.get_device_channels(device_id)

    def normalize_device(self, api_data: dict[str, Any]) -> NormalizedChassis | None:
        """Normalize one Shure System API device payload."""
        return SHURE_NORMALIZER.normalize_device(api_data)

    def normalize_channels(self, api_channels: list[dict[str, Any]]) -> list[NormalizedChannel]:
        """Normalize a Shure System API channel list."""
        return SHURE_NORMALIZER.normalize_channels(api_channels)

    @property
    def realtime_transport(self) -> RealtimeTransport:
        """Shure receivers stream over a WebSocket opened directly against the device."""
        return "websocket"

    async def subscribe_to_chassis(
        self,
        chassis: WirelessChassis,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Subscribe to one receiver over a WebSocket opened against its own address."""
        from . import websocket as websocket_module

        base_url = build_device_https_url(
            ip_address=chassis.ip,
            port=getattr(chassis, "port", 443),
        )
        client = await sync_to_async(ShureSystemAPIClient, thread_sensitive=True)(base_url=base_url)
        try:
            await websocket_module.connect_and_subscribe(
                client,
                chassis.api_device_id,
                callback,
            )
        finally:
            await sync_to_async(client.close, thread_sensitive=True)()

    def is_healthy(self) -> bool:
        """Check if the Shure API client is healthy."""
        return self.get_client().is_healthy()

    def check_health(self) -> dict[str, Any]:
        """Perform health check against Shure API."""
        return self.get_client().check_health()

    def add_discovery_ips(self, ips: list[str]) -> bool:
        """Add IP addresses to the Shure System API manual discovery list."""
        return self.get_client().discovery.add_discovery_ips(ips)

    def get_discovery_ips(self) -> list[str]:
        """Retrieve the current manual discovery IPs from Shure System API."""
        return self.get_client().discovery.get_discovery_ips()

    def remove_discovery_ips(self, ips: list[str]) -> bool:
        """Remove IP addresses from the Shure System API manual discovery list."""
        return self.get_client().discovery.remove_discovery_ips(ips)
