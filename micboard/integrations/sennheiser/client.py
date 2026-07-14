"""Core HTTP client for Sennheiser SSCv2 API with connection pooling and retry logic."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from micboard.services.common.base.client import BaseHTTPClient

from .device_client import SennheiserDeviceClient
from .discovery_client import SennheiserDiscoveryClient
from .exceptions import SennheiserAPIError, SennheiserAPIRateLimitError

logger = logging.getLogger(__name__)


class SennheiserSystemAPIClient(BaseHTTPClient):
    """Client for interacting with Sennheiser SSCv2 API with connection pooling and retry logic."""

    def __init__(self):
        """Initialize Sennheiser API client and compose sub-clients."""
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
        password = config.get("SENNHEISER_API_PASSWORD")

        if not isinstance(password, str) or not password:
            raise ValueError(
                "SENNHEISER_API_PASSWORD is required for Sennheiser SSCv2 API authentication"
            )
        self.password = password

        # HTTP Basic Auth
        self.client.auth = httpx.BasicAuth(self.username, self.password)

    def _get_health_check_endpoint(self) -> str:
        """Return health check endpoint for Sennheiser API."""
        return "/api/ssc/version"

    def get_exception_class(self) -> type[SennheiserAPIError]:
        """Return Sennheiser-specific API exception class."""
        return SennheiserAPIError

    def get_rate_limit_exception_class(self) -> type[SennheiserAPIRateLimitError]:
        """Return Sennheiser-specific rate limit exception class."""
        return SennheiserAPIRateLimitError

    async def connect_and_subscribe(self, device_id: str, callback) -> None:
        """Establishes WebSocket connection and subscribes to device updates.

        SSCv2 uses SSE for subscriptions, not WebSocket.
        """
        raise NotImplementedError("SSE subscription not yet implemented for Sennheiser")
