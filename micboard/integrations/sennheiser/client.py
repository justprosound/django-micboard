"""
Core HTTP client for Sennheiser SSCv2 API with connection pooling and retry logic.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from micboard.integrations.base_http_client import BaseHTTPClient, BasePollingMixin

from .device_client import SennheiserDeviceClient
from .discovery_client import SennheiserDiscoveryClient
from .exceptions import SennheiserAPIError, SennheiserAPIRateLimitError
from .transformers import SennheiserDataTransformer

logger = logging.getLogger(__name__)


class SennheiserSystemAPIClient(BasePollingMixin, BaseHTTPClient):
    """Client for interacting with Sennheiser SSCv2 API with connection pooling and retry logic."""

    def __init__(self):
        super().__init__()

        # Compose sub-clients
        self.discovery = SennheiserDiscoveryClient(self)
        self.devices = SennheiserDeviceClient(self)

    def _get_config_prefix(self) -> str:
        """Return configuration key prefix for Sennheiser API."""
        return "SENNHEISER_API"

    def _get_default_base_url(self) -> str:
        """Return default base URL for Sennheiser API."""
        return "https://localhost:443"

    def _configure_authentication(self, config: dict[str, Any]) -> None:
        """Configure Sennheiser API authentication with HTTP Basic Auth."""
        self.username = "api"
        self.password = config.get("SENNHEISER_API_PASSWORD")

        if not self.password:
            raise ValueError(
                "SENNHEISER_API_PASSWORD is required for Sennheiser SSCv2 API authentication"
            )

        # HTTP Basic Auth
        self.session.auth = (self.username, self.password)

    def _get_health_check_endpoint(self) -> str:
        """Return health check endpoint for Sennheiser API."""
        return "/api/ssc/version"

    def get_exception_class(self) -> type[Exception]:
        """Return Sennheiser-specific API exception class."""
        return SennheiserAPIError

    def get_rate_limit_exception_class(self) -> type[Exception]:
        """Return Sennheiser-specific rate limit exception class."""
        return SennheiserAPIRateLimitError

    def _get_transformer(self) -> SennheiserDataTransformer:
        """Return Sennheiser data transformer."""
        return SennheiserDataTransformer()

    async def connect_and_subscribe(self, device_id: str, callback) -> None:
        """Establishes WebSocket connection and subscribes to device updates.

        SSCv2 uses SSE for subscriptions, not WebSocket.
        """
        raise NotImplementedError("SSE subscription not yet implemented for Sennheiser")

    # --- Backwards-compatible delegations
    def get_devices(self):
        return self.devices.get_devices()

    def get_device(self, device_id: str):
        return self.devices.get_device(device_id)

    def get_device_channels(self, device_id: str):
        return self.devices.get_device_channels(device_id)

    def get_transmitter_data(self, device_id: str, channel: int):
        return self.devices.get_transmitter_data(device_id, channel)

    def get_device_identity(self, device_id: str):
        return self.devices.get_device_identity(device_id)

    def get_device_network(self, device_id: str):
        return self.devices.get_device_network(device_id)

    def get_device_status(self, device_id: str):
        return self.devices.get_device_status(device_id)

    def _enrich_device_data(self, device_id: str, device_data: dict[str, Any]):
        return self.devices._enrich_device_data(device_id, device_data)

    # Delegate discovery-related helpers to the discovery sub-client
    def add_discovery_ips(self, ips: list[str]) -> bool:
        return cast(bool, self.discovery.add_discovery_ips(ips))

    def get_discovery_ips(self) -> list[str]:
        return cast(list[str], self.discovery.get_discovery_ips())

    def remove_discovery_ips(self, ips: list[str]) -> bool:
        return cast(bool, self.discovery.remove_discovery_ips(ips))
