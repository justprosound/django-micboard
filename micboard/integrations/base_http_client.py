"""Base HTTP client with shared retry, pooling, health tracking, and error handling.

This module provides a common foundation for manufacturer-specific API clients,
eliminating code duplication across Shure, Sennheiser, and future integrations.
"""

from __future__ import annotations

import json
import logging
import time
from abc import abstractmethod
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from micboard.integrations.common.exceptions import APIError, APIRateLimitError
from micboard.manufacturers.base import BaseAPIClient
from micboard.services.monitoring.base_health_mixin import HealthCheckMixin

logger = logging.getLogger(__name__)


class BaseHTTPClient(BaseAPIClient, HealthCheckMixin):
    """Abstract HTTP client with connection pooling, retry logic, and health tracking.

    Provides common functionality for all manufacturer API clients:
    - Session management with connection pooling
    - Configurable retry strategy with backoff
    - Health tracking and monitoring (via HealthCheckMixin)
    - Comprehensive error handling with logging
    - Rate limit detection

    Subclasses must implement:
    - _get_config_prefix(): Return config key prefix (e.g., "SHURE_API")
    - _configure_authentication(): Set up session auth headers/params
    - _get_health_check_endpoint(): Return endpoint for health checks
    - get_exception_class(): Return manufacturer-specific exception class
    - get_rate_limit_exception_class(): Return rate limit exception class
    """

    def __init__(self, base_url: str | None = None, verify_ssl: bool | None = None):
        """Initialize HTTP client with configuration.

        Args:
            base_url: Override base URL from config
            verify_ssl: Override SSL verification from config
        """
        from micboard.apps import MicboardConfig

        config = MicboardConfig.get_config()
        prefix = self._get_config_prefix()

        # Core configuration
        self.base_url = (
            base_url
            if base_url is not None
            else config.get(f"{prefix}_BASE_URL", self._get_default_base_url()).rstrip("/")
        )
        self.timeout = config.get(f"{prefix}_TIMEOUT", 10)
        self.verify_ssl = (
            verify_ssl if verify_ssl is not None else config.get(f"{prefix}_VERIFY_SSL", True)
        )

        # Retry configuration
        self.max_retries = config.get(f"{prefix}_MAX_RETRIES", 3)
        self.retry_backoff = config.get(f"{prefix}_RETRY_BACKOFF", 0.5)  # seconds
        self.retry_status_codes = config.get(
            f"{prefix}_RETRY_STATUS_CODES", [429, 500, 502, 503, 504]
        )

        # Connection health tracking
        self._last_successful_request: float | None = None
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

        # Circuit breaker configuration (per-client)
        failure_threshold = config.get(f"{prefix}_CIRCUIT_FAILURE_THRESHOLD", 5)
        recovery_timeout = config.get(f"{prefix}_CIRCUIT_RECOVERY_TIMEOUT", 60)
        self._circuit = CircuitBreaker(
            name=prefix, failure_threshold=failure_threshold, recovery_timeout=recovery_timeout
        )

        # Subclass-specific authentication setup
        self._configure_authentication(config)

    @abstractmethod
    def _get_config_prefix(self) -> str:
        """Return configuration key prefix for this manufacturer.

        Examples: "SHURE_API", "SENNHEISER_API"
        """
        raise NotImplementedError()

    @abstractmethod
    def _get_default_base_url(self) -> str:
        """Return default base URL if not configured."""
        raise NotImplementedError()

    @abstractmethod
    def _configure_authentication(self, config: dict[str, Any]) -> None:
        """Configure authentication for the session.

        Implementations should validate required credentials and update
        self.session.headers or self.session.auth as needed.

        Args:
            config: MICBOARD_CONFIG dictionary from Django settings

        Raises:
            ValueError: If required credentials are missing
        """
        raise NotImplementedError()

    @abstractmethod
    def _get_health_check_endpoint(self) -> str:
        """Return endpoint path for health checks.

        Examples: "/api/v1/devices", "/api/ssc/version"
        """
        raise NotImplementedError()

    @abstractmethod
    def get_exception_class(self) -> type[APIError]:
        """Return manufacturer-specific API exception class."""
        raise NotImplementedError()

    @abstractmethod
    def get_rate_limit_exception_class(self) -> type[APIRateLimitError]:
        """Return manufacturer-specific rate limit exception class."""
        raise NotImplementedError()

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
        """Perform health check against the API.

        Returns standardized health response from HealthCheckMixin:
        {
            "status": "healthy" | "degraded" | "unhealthy" | "error",
            "timestamp": ISO string,
            "details": {...}
        }
        """
        try:
            endpoint = self._get_health_check_endpoint()
            response = self.session.get(
                f"{self.base_url}{endpoint}",
                timeout=5,
                verify=self.verify_ssl,
            )

            is_healthy = response.status_code == 200
            status = "healthy" if is_healthy else "unhealthy"

            # Build details dict
            details = {
                "base_url": self.base_url,
                "status_code": response.status_code,
                "consecutive_failures": self._consecutive_failures,
                "last_successful_request": self._last_successful_request,
            }

            # Use mixin method to standardize response
            return self._standardize_health_response(
                status=status,
                details=details,
            )

        except requests.RequestException as e:
            return self._standardize_health_response(
                status="error",
                error=f"Health check failed: {e}",
            )

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Any | None:
        """Make HTTP request with error handling and comprehensive logging.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (e.g., "/api/v1/devices")
            **kwargs: Additional arguments for requests.request()

        Returns:
            Parsed JSON response or None on error

        Raises:
            Manufacturer-specific exceptions for errors
        """
        url = f"{self.base_url}{endpoint}"
        logger.debug("Making %s request to %s", method, url)
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", self.verify_ssl)

        # Fast-fail if circuit breaker is open for this client
        if getattr(self, "_circuit", None) and not self._circuit.allow_request():
            logger.error(
                "Circuit open for %s; failing fast for %s %s",
                self._get_config_prefix(),
                method,
                url,
            )
            raise CircuitOpenError(f"Circuit open for {self._get_config_prefix()}")

        try:
            response = self.session.request(method, url, **kwargs)
            return self._handle_response(response, method, url)
        except requests.exceptions.HTTPError as e:
            if getattr(self, "_circuit", None):
                try:
                    self._circuit.record_failure()
                except Exception:
                    logger.debug("Circuit record_failure failed", exc_info=True)
            self._handle_http_error(e, method, url)
        except requests.exceptions.ConnectionError as e:
            if getattr(self, "_circuit", None):
                try:
                    self._circuit.record_failure()
                except Exception:
                    logger.debug("Circuit record_failure failed", exc_info=True)
            self._handle_connection_error(e, method, url)
        except requests.exceptions.Timeout as e:
            if getattr(self, "_circuit", None):
                try:
                    self._circuit.record_failure()
                except Exception:
                    logger.debug("Circuit record_failure failed", exc_info=True)
            self._handle_timeout_error(e, method, url)
        except requests.RequestException as e:
            if getattr(self, "_circuit", None):
                try:
                    self._circuit.record_failure()
                except Exception:
                    logger.debug("Circuit record_failure failed", exc_info=True)
            self._handle_request_error(e, method, url)
        except json.JSONDecodeError as e:
            if getattr(self, "_circuit", None):
                try:
                    self._circuit.record_failure()
                except Exception:
                    logger.debug("Circuit record_failure failed", exc_info=True)
            self._handle_json_error(e, method, url)
        return None

    def _handle_response(self, response: requests.Response, method: str, url: str) -> Any | None:
        """Handle successful response and potential errors."""
        status = getattr(response, "status_code", None)

        if status is not None and status >= 400:
            # Record failure on server errors and rate-limits to trip circuit if needed
            if getattr(self, "_circuit", None) and (status >= 500 or status == 429):
                try:
                    self._circuit.record_failure()
                except Exception:
                    logger.debug("Circuit record_failure failed", exc_info=True)

            self._consecutive_failures += 1
            self._is_healthy = False if status >= 500 else self._is_healthy

            if status == 429:
                retry_after = self._extract_retry_after(response)
                logger.error("API HTTP 429 rate limit: %s %s", method, url)
                rate_limit_exc = self.get_rate_limit_exception_class()
                raise rate_limit_exc(
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
            api_exc = self.get_exception_class()
            raise api_exc(
                message=f"HTTP error for {method} {url}",
                status_code=status,
                response=response,
            ) from None

        # Update health tracking on success
        self._last_successful_request = time.time()
        self._consecutive_failures = 0
        self._is_healthy = True

        # Inform circuit breaker of success so it can close / reset
        if getattr(self, "_circuit", None):
            try:
                self._circuit.record_success()
            except Exception:
                logger.debug("Circuit record_success failed", exc_info=True)

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
            return None
        return None

    def _handle_http_error(self, e: requests.exceptions.HTTPError, method: str, url: str) -> None:
        """Handle HTTPError exceptions."""
        status_code = getattr(e.response, "status_code", None)
        # Record failure for server errors and rate-limits
        if (
            getattr(self, "_circuit", None)
            and status_code is not None
            and (status_code >= 500 or status_code == 429)
        ):
            try:
                self._circuit.record_failure()
            except Exception:
                logger.debug("Circuit record_failure failed", exc_info=True)

        self._consecutive_failures += 1
        if status_code == 429:
            rate_limit_exc = self.get_rate_limit_exception_class()
            raise rate_limit_exc(
                message=f"Rate limit exceeded for {method} {url}", response=e.response
            ) from e
        logger.error(
            "API HTTP error: %s %s - Status %d: %s",
            method,
            url,
            status_code,
            e.response.text[:200],  # Limit error text length
        )
        api_exc = self.get_exception_class()
        raise api_exc(
            message=f"HTTP error for {method} {url}",
            status_code=status_code,
            response=e.response,
        ) from e

    def _handle_connection_error(
        self, e: requests.exceptions.ConnectionError, method: str, url: str
    ) -> None:
        """Handle ConnectionError exceptions."""
        # Record failure on connection errors
        if getattr(self, "_circuit", None):
            try:
                self._circuit.record_failure()
            except Exception:
                logger.debug("Circuit record_failure failed", exc_info=True)

        self._consecutive_failures += 1
        self._is_healthy = False
        logger.error("API connection error: %s %s - %s", method, url, e)
        api_exc = self.get_exception_class()
        raise api_exc(f"Connection error to {url}", response=None) from e

    def _handle_timeout_error(self, e: requests.exceptions.Timeout, method: str, url: str) -> None:
        """Handle Timeout exceptions."""
        # Record failure on timeout
        if getattr(self, "_circuit", None):
            try:
                self._circuit.record_failure()
            except Exception:
                logger.debug("Circuit record_failure failed", exc_info=True)

        self._consecutive_failures += 1
        logger.error("API timeout error: %s %s - %s", method, url, e)
        api_exc = self.get_exception_class()
        raise api_exc(f"Timeout error for {url}", response=None) from e

    def _handle_request_error(self, e: requests.RequestException, method: str, url: str) -> None:
        """Handle general RequestException."""
        # Record failure for general request exceptions
        if getattr(self, "_circuit", None):
            try:
                self._circuit.record_failure()
            except Exception:
                logger.debug("Circuit record_failure failed", exc_info=True)

        self._consecutive_failures += 1
        logger.error("API request failed: %s %s - %s", method, url, e)
        api_exc = self.get_exception_class()
        raise api_exc(f"Unknown request error for {url}", response=None) from e

    def _handle_json_error(self, e: json.JSONDecodeError, method: str, url: str) -> None:
        """Handle JSONDecodeError."""
        # Record failure for invalid JSON responses
        if getattr(self, "_circuit", None):
            try:
                self._circuit.record_failure()
            except Exception:
                logger.debug("Circuit record_failure failed", exc_info=True)

        self._consecutive_failures += 1
        logger.error("Failed to parse JSON response from %s %s: %s", method, url, e)
        api_exc = self.get_exception_class()
        raise api_exc(f"Invalid JSON response from {url}", response=None) from e


class BasePollingMixin:
    """Mixin for common device polling logic.

    Provides poll_all_devices() implementation that works with any transformer
    that follows the standard interface.
    """

    def poll_all_devices(self) -> dict[str, dict[str, Any]]:
        """Poll all devices using the top-level client methods.

        Returns:
            Dictionary mapping device IDs to transformed device data
        """
        transformer = self._get_transformer()

        try:
            devices = self.get_devices()  # type: ignore[attr-defined]
            logger.info("Polling %d devices from %s API", len(devices), self.__class__.__name__)
        except CircuitOpenError:
            logger.warning("Circuit open for %s; skipping device polling", self.__class__.__name__)
            return {}
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

    def _poll_single_device(self, device_id: str, transformer: Any) -> dict[str, Any] | None:
        """Poll a single device and return transformed data."""
        try:
            device_data = self.get_device(device_id)  # type: ignore[attr-defined]
            if not device_data:
                logger.warning("No data returned for device %s", device_id)
                return None

            try:
                device_data = self._enrich_device_data(device_id, device_data)  # type: ignore[attr-defined]
            except Exception:
                logger.debug("Enrichment failed for device %s", device_id)

            channels = self.get_device_channels(device_id)  # type: ignore[attr-defined]
            device_data["channels"] = channels

            transformed = transformer.transform_device_data(device_data)
            if transformed:
                return transformed
            else:
                logger.warning("Failed to transform data for device %s", device_id)
                return None
        except CircuitOpenError:
            logger.warning(
                "Circuit open for %s while polling device %s; skipping",
                self.__class__.__name__,
                device_id,
            )
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

    @abstractmethod
    def _get_transformer(self) -> Any:
        """Return manufacturer-specific data transformer."""
        raise NotImplementedError()


class CircuitOpenError(APIError):
    """Raised when a circuit breaker is open for an endpoint."""


class CircuitBreaker:
    """Simple in-process circuit breaker.

    Note: This is an in-memory, per-process circuit breaker intended to prevent
    hammering of unhealthy external services. For multi-process deployments,
    consider using a shared store (Redis) to coordinate state.
    """

    def __init__(
        self, *, name: str | None = None, failure_threshold: int = 5, recovery_timeout: int = 60
    ):
        """Initialize circuit breaker settings."""
        self.name = name
        self.failure_threshold = int(failure_threshold)
        self.recovery_timeout = int(recovery_timeout)
        self._failures = 0
        self._last_failure = 0.0
        self._state = "closed"  # one of "closed", "open", "half-open"

    def allow_request(self) -> bool:
        """Return True if a request is allowed (circuit closed or half-open)."""
        if self._state == "open":
            if (time.time() - self._last_failure) > self.recovery_timeout:
                self._state = "half-open"
                logger.info("Circuit half-open for %s", self.name or "unknown")
                return True
            return False
        return True

    def record_success(self) -> None:
        """Record a successful call and close the circuit."""
        prev = self._state
        self._failures = 0
        self._state = "closed"
        if prev in ("open", "half-open"):
            logger.info("Circuit closed for %s", self.name or "unknown")
            try:
                from datetime import datetime

                from micboard.metrics import MetricsCollector, ServiceMetric

                MetricsCollector.record_metric(
                    ServiceMetric(
                        service_name=self.name or "external_api",
                        method_name="circuit_closed",
                        duration_ms=0.0,
                        timestamp=datetime.now(),
                        success=True,
                    )
                )
            except Exception:
                logger.debug("Metrics recording for circuit_closed failed", exc_info=True)

    def record_failure(self) -> None:
        """Record a failed call and open the circuit if threshold reached."""
        prev = self._state
        self._failures += 1
        self._last_failure = time.time()
        if self._failures >= self.failure_threshold:
            self._state = "open"
            if prev != "open":
                logger.warning(
                    "Circuit opened for %s after %d failures",
                    self.name or "external_api",
                    self._failures,
                )
                try:
                    from datetime import datetime

                    from micboard.metrics import MetricsCollector, ServiceMetric

                    MetricsCollector.record_metric(
                        ServiceMetric(
                            service_name=self.name or "external_api",
                            method_name="circuit_open",
                            duration_ms=0.0,
                            timestamp=datetime.now(),
                            success=False,
                            error_message="failure_threshold_exceeded",
                            metadata={"failures": self._failures},
                        )
                    )
                except Exception:
                    logger.debug("Metrics recording for circuit_open failed", exc_info=True)

    @property
    def state(self) -> str:
        return self._state


def create_resilient_session(
    *,
    max_retries: int = 3,
    backoff_factor: float = 0.5,
    status_forcelist: list[int] | None = None,
    pool_connections: int = 10,
    pool_maxsize: int = 20,
) -> requests.Session:
    """Create a requests.Session configured with urllib3 Retry and pooling."""
    session = requests.Session()
    status_forcelist = status_forcelist or [429, 500, 502, 503, 504]
    retry = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry, pool_connections=pool_connections, pool_maxsize=pool_maxsize
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
