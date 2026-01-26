"""Core HTTP client for Shure System API with connection pooling and retry logic."""

from __future__ import annotations

import logging
from typing import Any, cast

from django.conf import settings
from requests.auth import HTTPDigestAuth

from micboard.integrations.base_http_client import BaseHTTPClient, BasePollingMixin

from .device_client import ShureDeviceClient
from .discovery_client import ShureDiscoveryClient
from .exceptions import ShureAPIError, ShureAPIRateLimitError
from .transformers import ShureDataTransformer

logger = logging.getLogger(__name__)


class ShureSystemAPIClient(BasePollingMixin, BaseHTTPClient):
    """Client for interacting with Shure System API with connection pooling and retry logic."""

    def __init__(self, base_url: str | None = None, verify_ssl: bool | None = None):
        super().__init__(base_url, verify_ssl)
        config = getattr(settings, "MICBOARD_CONFIG", {})

        # Respect an explicit websocket URL from config; store it on a
        # private attribute because `websocket_url` is a read-only property.
        explicit_ws = config.get("SHURE_API_WEBSOCKET_URL") if config is not None else None
        # Track whether an explicit websocket URL was provided (even if None)
        if "SHURE_API_WEBSOCKET_URL" in config:
            self._explicit_websocket_set = True
            self._explicit_websocket_url = explicit_ws
        else:
            self._explicit_websocket_set = False
            self._explicit_websocket_url = None

        # Compose sub-clients
        self.discovery = ShureDiscoveryClient(self)
        self.devices = ShureDeviceClient(self)

    def _get_config_prefix(self) -> str:
        """Return configuration key prefix for Shure API."""
        return "SHURE_API"

    def _get_default_base_url(self) -> str:
        """Return default base URL for Shure API."""
        return "https://localhost:10000"

    def _configure_authentication(self, config: dict[str, Any]) -> None:
        """Configure Shure API authentication.

        The Shure System API can use multiple authentication methods:
        1. API Key header (x-api-key) - primary per Swagger securitySchemes
        2. HTTP Digest Authentication (RFC 7616) - optional, controlled by config
        3. Bearer token - in Authorization header (reserved)
        """
        self.shared_key = config.get("SHURE_API_SHARED_KEY")
        if not self.shared_key:
            raise ValueError("SHURE_API_SHARED_KEY is required for Shure System API authentication")

        # Prefer x-api-key per Swagger 'SharedSecret' security scheme
        self.session.headers.update({"x-api-key": str(self.shared_key)})

        # Optional: enable HTTP Digest if explicitly configured
        use_digest = bool(config.get("SHURE_API_USE_DIGEST", False))
        if use_digest:
            try:
                self.session.auth = HTTPDigestAuth(username="shure", password=self.shared_key)
            except Exception as e:
                logger.warning(
                    f"HTTP Digest Auth setup failed: {e}. Continuing with x-api-key header only"
                )

    def _get_health_check_endpoint(self) -> str:
        """Return health check endpoint for Shure API."""
        return "/api/v1/devices"

    def get_exception_class(self) -> type[Exception]:
        """Return Shure-specific API exception class."""
        return ShureAPIError

    def get_rate_limit_exception_class(self) -> type[Exception]:
        """Return Shure-specific rate limit exception class."""
        return ShureAPIRateLimitError

    def _get_transformer(self) -> ShureDataTransformer:
        """Return Shure data transformer."""
        return ShureDataTransformer()

    @property
    def websocket_url(self) -> str | None:
        """Return the websocket URL, preferring an explicit config value.

        This is a property so changes to `base_url` after initialization are
        reflected in tests and runtime usage.
        """
        # If callers explicitly set the websocket value (including explicit
        # None), prefer that over dynamic inference.
        if getattr(self, "_explicit_websocket_set", False):
            return self._explicit_websocket_url
        if not getattr(self, "base_url", None):
            return None
        ws_scheme = "wss" if self.base_url.startswith("https") else "ws"
        base = self.base_url.split("://", 1)[1]
        return f"{ws_scheme}://{base}/api/v1/subscriptions/websocket/create"

    @websocket_url.setter
    def websocket_url(self, value: str | None) -> None:
        """Allow tests or callers to explicitly set the websocket URL.

        This writes to a private attribute which the property prefers when
        present.
        """
        self._explicit_websocket_url = value
        self._explicit_websocket_set = True

    async def connect_and_subscribe(self, device_id: str, callback) -> None:
        """Establishes WebSocket connection and subscribes to device updates.

        Args:
            device_id: The Shure API device ID to subscribe to
            callback: Function to call with received WebSocket messages

        Raises:
            ShureAPIError: If connection or subscription fails
        """
        from .websocket import connect_and_subscribe

        return await connect_and_subscribe(self, device_id, callback)

    # --- Backwards-compatible delegations (tests expect these on top-level client)
    # Delegate device-related helpers to the device sub-client
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
