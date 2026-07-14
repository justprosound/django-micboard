"""Core HTTP client for Shure System API with connection pooling and retry logic."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from micboard.services.common.base.client import BaseHTTPClient
from micboard.utils.exception_logging import sanitized_exception_info

from .device_client import ShureDeviceClient
from .discovery_client import ShureDiscoveryClient
from .exceptions import ShureAPIError, ShureAPIRateLimitError

logger = logging.getLogger(__name__)


class ShureSystemAPIClient(BaseHTTPClient):
    """Client for interacting with Shure System API with connection pooling and retry logic."""

    def __init__(self, base_url: str | None = None, *, shared_key: str | None = None):
        """Initialize Shure API client, configure auth, and compose sub-clients."""
        from micboard.services.settings.settings_service import settings

        self._shared_key_override = shared_key
        config = settings.get_config_dict()
        explicit_ws = config.get("SHURE_API_WEBSOCKET_URL") if config is not None else None
        if explicit_ws is not None:
            self._validate_websocket_url(explicit_ws)

        super().__init__(base_url)

        # Respect an explicit websocket URL from config; store it on a
        # private attribute because `websocket_url` is a read-only property.
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
        self.shared_key = (
            self._shared_key_override
            if self._shared_key_override is not None
            else config.get("SHURE_API_SHARED_KEY")
        )
        if not self.shared_key:
            raise ValueError("SHURE_API_SHARED_KEY is required for Shure System API authentication")

        # Prefer x-api-key per Swagger 'SharedSecret' security scheme
        self.client.headers.update({"x-api-key": str(self.shared_key)})

        # Optional: enable HTTP Digest if explicitly configured
        use_digest = bool(config.get("SHURE_API_USE_DIGEST", False))
        if use_digest:
            try:
                self.client.auth = httpx.DigestAuth(
                    username="shure",
                    password=str(self.shared_key),
                )
            except Exception as exc:
                logger.warning(
                    "HTTP Digest Auth setup failed; continuing with x-api-key header only",
                    exc_info=sanitized_exception_info(exc),
                )

    def _get_health_check_endpoint(self) -> str:
        """Return health check endpoint for Shure API."""
        return "/api/v1/devices"

    def get_exception_class(self) -> type[ShureAPIError]:
        """Return Shure-specific API exception class."""
        return ShureAPIError

    def get_rate_limit_exception_class(self) -> type[ShureAPIRateLimitError]:
        """Return Shure-specific rate limit exception class."""
        return ShureAPIRateLimitError

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
        if value is not None:
            self._validate_websocket_url(value)
        self._explicit_websocket_url = value
        self._explicit_websocket_set = True

    @staticmethod
    def _validate_websocket_url(value: str) -> None:
        """Reject malformed or cleartext manufacturer WebSocket URLs."""
        try:
            parsed_url = httpx.URL(value)
        except (TypeError, httpx.InvalidURL) as exc:
            raise ValueError("SHURE_API_WEBSOCKET_URL must be an absolute WSS URL") from exc

        if parsed_url.scheme != "wss" or not parsed_url.host:
            raise ValueError("SHURE_API_WEBSOCKET_URL must be an absolute WSS URL")
