"""
Core HTTP client for Sennheiser SSCv2 API with connection pooling and retry logic.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, cast

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from micboard.manufacturers.base import BaseAPIClient

from .device_client import SennheiserDeviceClient
from .discovery_client import SennheiserDiscoveryClient
from .exceptions import SennheiserAPIError, SennheiserAPIRateLimitError
from .transformers import SennheiserDataTransformer

logger = logging.getLogger(__name__)


class SennheiserSystemAPIClient(BaseAPIClient):
    """Client for interacting with Sennheiser SSCv2 API with connection pooling and retry logic."""

    def __init__(self):
        config = getattr(settings, "MICBOARD_CONFIG", {})
        self.base_url = config.get("SENNHEISER_API_BASE_URL", "https://localhost:443").rstrip("/")
        self.username = "api"
        self.password = config.get("SENNHEISER_API_PASSWORD")
        self.timeout = config.get("SENNHEISER_API_TIMEOUT", 10)
        self.verify_ssl = config.get("SENNHEISER_API_VERIFY_SSL", True)

        # Retry configuration
        self.max_retries = config.get("SENNHEISER_API_MAX_RETRIES", 3)
        self.retry_backoff = config.get("SENNHEISER_API_RETRY_BACKOFF", 0.5)  # seconds
        self.retry_status_codes = config.get(
            "SENNHEISER_API_RETRY_STATUS_CODES", [429, 500, 502, 503, 504]
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

        if not self.password:
            raise ValueError("SENNHEISER_API_PASSWORD is required for Sennheiser SSCv2 API authentication")

        # HTTP Basic Auth
        self.session.auth = (self.username, self.password)

        # Compose sub-clients
        self.discovery = SennheiserDiscoveryClient(self)
        self.devices = SennheiserDeviceClient(self)

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
        """Perform health check against Sennheiser API."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/ssc/version",
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
            return self._handle_response(response, method, url)
        except requests.exceptions.HTTPError as e:
            self._handle_http_error(e, method, url)
        except requests.exceptions.ConnectionError as e:
            self._handle_connection_error(e, method, url)
        except requests.exceptions.Timeout as e:
            self._handle_timeout_error(e, method, url)
        except requests.RequestException as e:
            self._handle_request_error(e, method, url)
        except json.JSONDecodeError as e:
            self._handle_json_error(e, method, url)

    def _handle_response(self, response: requests.Response, method: str, url: str) -> Any | None:
        """Handle successful response and potential errors."""
        status = getattr(response, "status_code", None)

        if status is not None and status >= 400:
            self._consecutive_failures += 1
            self._is_healthy = False if status >= 500 else self._is_healthy

            if status == 429:
                retry_after = self._extract_retry_after(response)
                logger.error("API HTTP 429 rate limit: %s %s", method, url)
                raise SennheiserAPIRateLimitError(
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
            raise SennheiserAPIError(
                message=f"HTTP error for {method} {url}",
                status_code=status,
                response=response,
            ) from None

        # Update health tracking on success
        self._last_successful_request = time.time()
        self._consecutive_failures = 0
        self._is_healthy = True

        result = response.json() if response.content else None
        logger.debug("Request successful: %s %s", method, url)
        return result

    def _extract_retry_after(self, response: requests.Response) -> int | None:
        """Extract retry-after header value."""
        try:
            retry_after_header = response.headers.get("Retry-After")
            if retry_after_header is not None:
                return int(retry_after_header)
        except ValueError:
            pass
        return None

    def _handle_http_error(self, e: requests.exceptions.HTTPError, method: str, url: str) -> None:
        """Handle HTTPError exceptions."""
        self._consecutive_failures += 1
        if e.response.status_code == 429:
            raise SennheiserAPIRateLimitError(
                message=f"Rate limit exceeded for {method} {url}", response=e.response
            ) from e
        logger.error(
            "API HTTP error: %s %s - Status %d: %s",
            method,
            url,
            e.response.status_code,
            e.response.text[:200],  # Limit error text length
        )
        raise SennheiserAPIError(
            message=f"HTTP error for {method} {url}",
            status_code=e.response.status_code,
            response=e.response,
        ) from e

    def _handle_connection_error(self, e: requests.exceptions.ConnectionError, method: str, url: str) -> None:
        """Handle ConnectionError exceptions."""
        self._consecutive_failures += 1
        self._is_healthy = False
        logger.error("API connection error: %s %s - %s", method, url, e)
        raise SennheiserAPIError(f"Connection error to {url}", response=None) from e

    def _handle_timeout_error(self, e: requests.exceptions.Timeout, method: str, url: str) -> None:
        """Handle Timeout exceptions."""
        self._consecutive_failures += 1
        logger.error("API timeout error: %s %s - %s", method, url, e)
        raise SennheiserAPIError(f"Timeout error for {url}", response=None) from e

    def _handle_request_error(self, e: requests.RequestException, method: str, url: str) -> None:
        """Handle general RequestException."""
        self._consecutive_failures += 1
        logger.error("API request failed: %s %s - %s", method, url, e)
        raise SennheiserAPIError(f"Unknown request error for {url}", response=None) from e

    def _handle_json_error(self, e: json.JSONDecodeError, method: str, url: str) -> None:
        """Handle JSONDecodeError."""
        self._consecutive_failures += 1
        logger.error("Failed to parse JSON response from %s %s: %s", method, url, e)
        raise SennheiserAPIError(f"Invalid JSON response from {url}", response=None) from e

    async def connect_and_subscribe(self, device_id: str, callback):
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

    def poll_all_devices(self) -> dict[str, dict[str, Any]]:
        """Poll all devices using the top-level client methods."""
        from .transformers import SennheiserDataTransformer

        transformer = SennheiserDataTransformer()

        try:
            devices = self.get_devices()
            logger.info("Polling %d devices from Sennheiser SSCv2 API", len(devices))
        except Exception:
            logger.exception("Failed to get device list")
            return {}

        data: dict[str, dict[str, Any]] = {}
        for device in devices:
            device_id = device.get("id")
            if not device_id:
                logger.warning("Device missing 'id' field: %s", device)
                continue

            device_data = self._poll_single_device(device_id, transformer)
            if device_data:
                data[device_id] = device_data

        self._log_firmware_coverage(data)
        logger.info("Successfully polled %d devices", len(data))
        return data

    def _poll_single_device(self, device_id: str, transformer: SennheiserDataTransformer) -> dict[str, Any] | None:
        """Poll a single device and return transformed data."""
        try:
            device_data = self.get_device(device_id)
            if not device_data:
                logger.warning("No data returned for device %s", device_id)
                return None

            try:
                device_data = self._enrich_device_data(device_id, device_data)
            except Exception:
                logger.debug("Enrichment failed for device %s", device_id)

            channels = self.get_device_channels(device_id)
            device_data["channels"] = channels

            transformed = transformer.transform_device_data(device_data)
            if transformed:
                return transformed
            else:
                logger.warning("Failed to transform data for device %s", device_id)
                return None
        except Exception:
            logger.exception("Error polling device %s", device_id)
            return None

    def _log_firmware_coverage(self, data: dict[str, dict[str, Any]]) -> None:
        """Log firmware coverage information."""
        missing_fw = [d for d in data.values() if not d.get("firmware")]
        if missing_fw:
            logger.warning("%d devices missing firmware info", len(missing_fw))
        else:
            logger.info("Firmware info present for all devices")

    # Delegate discovery-related helpers to the discovery sub-client
    def add_discovery_ips(self, ips: list[str]) -> bool:
        return cast(bool, self.discovery.add_discovery_ips(ips))

    def get_discovery_ips(self) -> list[str]:
        return cast(list[str], self.discovery.get_discovery_ips())

    def remove_discovery_ips(self, ips: list[str]) -> bool:
        return cast(bool, self.discovery.remove_discovery_ips(ips))
