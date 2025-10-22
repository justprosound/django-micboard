"""
Core HTTP client for Shure System API with connection pooling and retry logic.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from micboard.manufacturers.base import BaseAPIClient

from .device_client import ShureDeviceClient
from .discovery_client import ShureDiscoveryClient
from .exceptions import ShureAPIError, ShureAPIRateLimitError

logger = logging.getLogger(__name__)


class ShureSystemAPIClient(BaseAPIClient):
    """Client for interacting with Shure System API with connection pooling and retry logic."""

    def __init__(self):
        config = getattr(settings, "MICBOARD_CONFIG", {})
        self.base_url = config.get("SHURE_API_BASE_URL", "http://localhost:8080").rstrip("/")
        self.shared_key = config.get("SHURE_API_SHARED_KEY")
        self.timeout = config.get("SHURE_API_TIMEOUT", 10)
        self.verify_ssl = config.get("SHURE_API_VERIFY_SSL", True)

        # Retry configuration
        self.max_retries = config.get("SHURE_API_MAX_RETRIES", 3)
        self.retry_backoff = config.get("SHURE_API_RETRY_BACKOFF", 0.5)  # seconds
        self.retry_status_codes = config.get(
            "SHURE_API_RETRY_STATUS_CODES", [429, 500, 502, 503, 504]
        )

        # Connection health tracking
        self._last_successful_request = None
        self._consecutive_failures = 0
        self._is_healthy = True

        # Create session with retry strategy and connection pooling
        self.session = requests.Session()

        # Connection pooling configuration
        adapter = HTTPAdapter(
            max_retries=self._create_retry_strategy(),
            pool_connections=10,  # Number of connection pools to cache
            pool_maxsize=20,  # Max connections per pool
            pool_block=False,  # Don't block if pool is full
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        if not self.shared_key:
            raise ValueError("SHURE_API_SHARED_KEY is required for Shure System API authentication")

        # The Shure System API supports a shared-secret style authentication.
        # Prefer the explicit API key header (x-api-key) per Swagger definition
        # while keeping Authorization: Bearer for backward compatibility.
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.shared_key}",
                "x-api-key": str(self.shared_key),
            }
        )

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

    def _create_retry_strategy(self) -> Retry:
        """Create retry strategy for HTTP requests."""
        return Retry(
            total=self.max_retries,
            backoff_factor=self.retry_backoff,
            status_forcelist=self.retry_status_codes,
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
            raise_on_status=False,  # Let us handle status errors
        )

    def is_healthy(self) -> bool:
        """Check if API client is healthy based on recent requests."""
        return self._is_healthy and self._consecutive_failures < 5

    def check_health(self) -> dict[str, Any]:
        """Perform health check against Shure API."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/health",
                timeout=5,
                verify=self.verify_ssl,
            )
            is_up = response.status_code == 200
            return {
                "status": "healthy" if is_up else "unhealthy",
                "base_url": self.base_url,
                "status_code": response.status_code,
                "consecutive_failures": self._consecutive_failures,
                "last_successful_request": self._last_successful_request,
            }
        except requests.RequestException as e:
            return {
                "status": "unreachable",
                "base_url": self.base_url,
                "error": str(e),
                "consecutive_failures": self._consecutive_failures,
                "last_successful_request": self._last_successful_request,
            }

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Any | None:
        """Make HTTP request with error handling and comprehensive logging."""
        url = f"{self.base_url}{endpoint}"
        logger.debug("Making %s request to %s", method, url)
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", self.verify_ssl)

        try:
            response = self.session.request(method, url, **kwargs)
            # Some tests use a Mock response that does not raise for
            # `raise_for_status()`. Ensure we handle non-2xx status codes
            # explicitly based on response.status_code.
            status = getattr(response, "status_code", None)

            if status is not None and status >= 400:
                # Update failure counters
                self._consecutive_failures += 1
                self._is_healthy = False if status >= 500 else self._is_healthy

                if status == 429:
                    # Rate limit handling
                    retry_after = None
                    try:
                        retry_after_header = response.headers.get("Retry-After")
                        if retry_after_header is not None:
                            retry_after = int(retry_after_header)
                    except ValueError:
                        # Retry-After header is not a valid integer, ignore it
                        pass
                    logger.error("API HTTP 429 rate limit: %s %s", method, url)
                    raise ShureAPIRateLimitError(
                        message=f"Rate limit exceeded for {method} {url}",
                        retry_after=retry_after,
                        response=response,
                    )

                logger.error(
                    "API HTTP error: %s %s - Status %s: %s",
                    method,
                    url,
                    status,
                    getattr(response, "text", "")[:200],
                )
                raise ShureAPIError(
                    message=f"HTTP error for {method} {url}",
                    status_code=status,
                    response=response,
                ) from None

            # Call raise_for_status to allow requests' own exceptions in real
            # scenarios (mocks may not raise).
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError as e:
                # This branch will generally be hit when raise_for_status
                # raises the HTTPError; mirror above handling.
                self._consecutive_failures += 1
                if e.response is not None and e.response.status_code == 429:
                    raise ShureAPIRateLimitError(
                        message=f"Rate limit exceeded for {method} {url}",
                        response=e.response,
                    ) from e
                raise ShureAPIError(
                    message=f"HTTP error for {method} {url}",
                    status_code=(e.response.status_code if e.response is not None else None),
                    response=(e.response if e.response is not None else None),
                ) from e

            # Update health tracking on success
            self._last_successful_request = time.time()
            self._consecutive_failures = 0
            self._is_healthy = True

            result = response.json() if response.content else None
            logger.debug("Request successful: %s %s", method, url)
            return result
        except requests.exceptions.HTTPError as e:
            self._consecutive_failures += 1
            if e.response.status_code == 429:
                raise ShureAPIRateLimitError(
                    message=f"Rate limit exceeded for {method} {url}", response=e.response
                ) from e
            logger.error(
                "API HTTP error: %s %s - Status %d: %s",
                method,
                url,
                e.response.status_code,
                e.response.text[:200],  # Limit error text length
            )
            raise ShureAPIError(
                message=f"HTTP error for {method} {url}",
                status_code=e.response.status_code,
                response=e.response,
            ) from e
        except requests.exceptions.ConnectionError as e:
            self._consecutive_failures += 1
            self._is_healthy = False
            logger.error("API connection error: %s %s - %s", method, url, e)
            raise ShureAPIError(f"Connection error to {url}", response=None) from e
        except requests.exceptions.Timeout as e:
            self._consecutive_failures += 1
            logger.error("API timeout error: %s %s - %s", method, url, e)
            raise ShureAPIError(f"Timeout error for {url}", response=None) from e
        except requests.RequestException as e:
            self._consecutive_failures += 1
            logger.error("API request failed: %s %s - %s", method, url, e)
            raise ShureAPIError(f"Unknown request error for {url}", response=None) from e
        except json.JSONDecodeError as e:
            self._consecutive_failures += 1
            logger.error("Failed to parse JSON response from %s %s: %s", method, url, e)
            raise ShureAPIError(f"Invalid JSON response from {url}", response=None) from e

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
        return f"{ws_scheme}://{self.base_url.split('://', 1)[1]}/api/v1/subscriptions/websocket/create"

    @websocket_url.setter
    def websocket_url(self, value: str | None) -> None:
        """Allow tests or callers to explicitly set the websocket URL.

        This writes to a private attribute which the property prefers when
        present.
        """
        self._explicit_websocket_url = value
        self._explicit_websocket_set = True

    async def connect_and_subscribe(self, device_id: str, callback):
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

    def poll_all_devices(self) -> dict[str, dict[str, Any]]:
        """Poll all devices using the top-level client methods.

        Tests patch the top-level ShureSystemAPIClient methods (get_devices,
        get_device, get_device_channels, _enrich_device_data) so implement the
        polling logic here and call those methods. Use the shared data
        transformer for compatibility with the device client implementation.
        """
        from .transformers import ShureDataTransformer

        transformer = ShureDataTransformer()

        try:
            devices = self.get_devices()
            logger.info("Polling %d devices from Shure System API", len(devices))
        except Exception:
            logger.exception("Failed to get device list")
            return {}

        data: dict[str, dict[str, Any]] = {}
        for device in devices:
            device_id = device.get("id")
            if not device_id:
                logger.warning("Device missing 'id' field: %s", device)
                continue

            try:
                device_data = self.get_device(device_id)
                if not device_data:
                    logger.warning("No data returned for device %s", device_id)
                    continue

                try:
                    device_data = self._enrich_device_data(device_id, device_data)
                except Exception:
                    logger.debug("Enrichment failed for device %s", device_id)

                channels = self.get_device_channels(device_id)
                device_data["channels"] = channels

                transformed = transformer.transform_device_data(device_data)
                if transformed:
                    data[device_id] = transformed
                else:
                    logger.warning("Failed to transform data for device %s", device_id)
            except Exception:
                logger.exception("Error polling device %s", device_id)
                continue

        missing_fw = [d for d in data.values() if not d.get("firmware")]
        if missing_fw:
            logger.warning("%d devices missing firmware info", len(missing_fw))
        else:
            logger.info("Firmware info present for all devices")

        logger.info("Successfully polled %d devices", len(data))
        return data

    # Delegate discovery-related helpers to the discovery sub-client
    def add_discovery_ips(self, ips: list[str]) -> bool:
        return self.discovery.add_discovery_ips(ips)

    def get_discovery_ips(self) -> list[str]:
        return self.discovery.get_discovery_ips()

    def remove_discovery_ips(self, ips: list[str]) -> bool:
        return self.discovery.remove_discovery_ips(ips)
