from __future__ import annotations

import logging
import math
import time
from abc import ABC, abstractmethod
from json import JSONDecodeError
from typing import Any, NoReturn, Self

import httpx
from httpx import RequestError, TimeoutException

from micboard.exceptions import APIError, APIRateLimitError
from micboard.services.common.base.bounded_transport import BoundedHTTPTransport
from micboard.services.common.network_limits import HTTPClientLimits
from micboard.services.monitoring.base_health_mixin import HealthCheckMixin
from micboard.utils.exception_logging import sanitized_exception_info

from .circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class BaseAPIClient(ABC):
    """Base API client interface."""

    @abstractmethod
    def is_healthy(self) -> bool:
        """Check if the client is healthy."""
        raise NotImplementedError()

    @abstractmethod
    def check_health(self) -> dict[str, Any]:
        """Perform a health check and return details."""
        raise NotImplementedError()

    @abstractmethod
    def _make_request(
        self, method: str, endpoint: str, **request_kwargs: Any
    ) -> dict[str, Any] | list[Any] | str | None:
        """Make an HTTP request."""
        raise NotImplementedError()


class BaseHTTPClient(BaseAPIClient, HealthCheckMixin):
    """Base HTTP client with circuit breaker and retries."""

    def __init__(self, base_url: str | None = None) -> None:
        """Initialize the HTTP client."""
        from micboard.services.settings.settings_service import settings

        config_dict = settings.get_config_dict()
        prefix = self._get_config_prefix()

        self.base_url = (
            base_url
            if base_url is not None
            else config_dict.get(f"{prefix}_BASE_URL", self._get_default_base_url()).rstrip("/")
        )
        self._validate_base_url(prefix)
        self.timeout = config_dict.get(f"{prefix}_TIMEOUT", 10)
        self.max_retries = config_dict.get(f"{prefix}_MAX_RETRIES", 3)
        self.retry_backoff = config_dict.get(f"{prefix}_RETRY_BACKOFF", 0.5)
        self.retry_status_codes = config_dict.get(
            f"{prefix}_RETRY_STATUS_CODES", [429, 500, 502, 503, 504]
        )
        self.http_limits = HTTPClientLimits.from_settings()

        self._last_successful_request: float | None = None
        self._consecutive_failures = 0
        self._is_healthy = True

        # httpx verifies certificates by default and honors SSL_CERT_FILE / SSL_CERT_DIR
        # for private certificate authorities. Certificate verification is mandatory.
        self.client = httpx.Client(timeout=self.timeout)

        failure_threshold = config_dict.get(f"{prefix}_CIRCUIT_FAILURE_THRESHOLD", 5)
        recovery_timeout = config_dict.get(f"{prefix}_CIRCUIT_RECOVERY_TIMEOUT", 60)
        self._circuit = CircuitBreaker(
            name=prefix, failure_threshold=failure_threshold, recovery_timeout=recovery_timeout
        )

        self._configure_authentication(config_dict)

    def _validate_base_url(self, prefix: str) -> None:
        """Reject malformed or cleartext URLs before credentials are configured."""
        try:
            parsed_url = httpx.URL(self.base_url)
        except (TypeError, httpx.InvalidURL) as exc:
            raise ValueError(f"{prefix}_BASE_URL must be an absolute HTTPS URL") from exc

        if (
            parsed_url.scheme != "https"
            or not parsed_url.host
            or parsed_url.username
            or parsed_url.password
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError(f"{prefix}_BASE_URL must be an absolute HTTPS URL")

    @abstractmethod
    def _get_config_prefix(self) -> str:
        """Get the configuration prefix for this client."""
        raise NotImplementedError()

    @abstractmethod
    def _get_default_base_url(self) -> str:
        """Get the default base URL for this client."""
        raise NotImplementedError()

    @abstractmethod
    def _configure_authentication(self, config: dict[str, Any]) -> None:
        """Configure authentication for the client."""
        raise NotImplementedError()

    @abstractmethod
    def _get_health_check_endpoint(self) -> str:
        """Get the health check endpoint."""
        raise NotImplementedError()

    @abstractmethod
    def get_exception_class(self) -> type[APIError]:
        """Get the exception class for API errors."""
        raise NotImplementedError()

    @abstractmethod
    def get_rate_limit_exception_class(self) -> type[APIRateLimitError]:
        """Get the exception class for rate limit errors."""
        raise NotImplementedError()

    def _create_retry_strategy(self) -> dict[str, Any]:
        """Return retry configuration for manual retry loop."""
        return {
            "total": self.max_retries,
            "backoff_factor": self.retry_backoff,
            "status_forcelist": self.retry_status_codes,
            "allowed_methods": ["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
            "raise_on_status": False,
        }

    def is_healthy(self) -> bool:
        return self._is_healthy and self._consecutive_failures < 5

    def check_health(self) -> dict[str, Any]:
        try:
            endpoint = self._get_health_check_endpoint()
            response = self._send_bounded_request(
                "GET",
                f"{self.base_url}{endpoint}",
                timeout=5,
            )

            is_healthy = response.status_code == 200
            status = "healthy" if is_healthy else "unhealthy"

            details = {
                "base_url": self.base_url,
                "status_code": response.status_code,
                "consecutive_failures": self._consecutive_failures,
                "last_successful_request": self._last_successful_request,
            }

            return self._standardize_health_response(
                status=status,
                details=details,
            )

        except (APIError, RequestError) as exc:
            logger.exception(
                "Health check request failed for %s",
                self._get_config_prefix(),
                exc_info=sanitized_exception_info(exc),
            )
            return self._standardize_health_response(
                status="error",
                error=f"Health check failed ({type(exc).__name__}); details redacted.",
            )

    def _make_request(
        self, method: str, endpoint: str, **request_kwargs: Any
    ) -> dict[str, Any] | list[Any] | str | None:
        url = f"{self.base_url}{endpoint}"
        logger.debug("Making %s request for %s", method, self._get_config_prefix())
        request_kwargs.setdefault("timeout", self.timeout)

        if getattr(self, "_circuit", None) and not self._circuit.allow_request():
            logger.error(
                "Circuit open for %s; failing fast for %s request",
                self._get_config_prefix(),
                method,
            )
            api_exc = self.get_exception_class()
            raise api_exc(
                f"Circuit open for {self._get_config_prefix()}",
                code="API_CIRCUIT_OPEN",
            )

        retry_strategy = self._create_retry_strategy()
        max_retries = retry_strategy["total"]
        retry_status_codes = set(retry_strategy["status_forcelist"])

        attempt = 0
        while True:
            try:
                response = self._send_bounded_request(method, url, **request_kwargs)
            except RequestError as exc:
                self._record_request_failure()
                if attempt < max_retries:
                    logger.exception(
                        "API request failed for %s; retrying attempt %d/%d: %s",
                        self._get_config_prefix(),
                        attempt + 1,
                        max_retries,
                        method,
                        exc_info=sanitized_exception_info(exc),
                    )
                    self._sleep_before_retry(attempt)
                    attempt += 1
                    continue

                api_exc = self.get_exception_class()
                if isinstance(exc, TimeoutException):
                    logger.exception(
                        "API timeout for %s %s request",
                        self._get_config_prefix(),
                        method,
                        exc_info=sanitized_exception_info(exc),
                    )
                    raise api_exc("Timeout error; details redacted", response=None) from exc

                logger.exception(
                    "API connection error for %s %s request",
                    self._get_config_prefix(),
                    method,
                    exc_info=sanitized_exception_info(exc),
                )
                raise api_exc("Connection error; details redacted", response=None) from exc
            except APIError:
                raise
            except Exception as exc:
                self._record_request_failure()
                logger.exception(
                    "Unexpected API request failure for %s %s request",
                    self._get_config_prefix(),
                    method,
                    exc_info=sanitized_exception_info(exc),
                )
                api_exc = self.get_exception_class()
                raise api_exc("Unknown request error; details redacted", response=None) from exc

            if response.status_code in retry_status_codes and attempt < max_retries:
                self._record_request_failure()
                self._sleep_before_retry(attempt, response=response)
                attempt += 1
                continue

            # Keep response handling outside the request exception block. This preserves
            # canonical API/rate-limit exceptions raised by `_handle_response`.
            return self._handle_response(response, method, url)

    def _send_bounded_request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Read a successful decoded response under a strict byte ceiling."""
        return self._bounded_transport().send(method, url, **kwargs)

    def _bounded_transport(self) -> BoundedHTTPTransport:
        """Bind the deep transport adapter to the client's current mutable configuration."""
        return BoundedHTTPTransport(
            client=self.client,
            limits=self.http_limits,
            oversized_response=self._raise_oversized_response,
        )

    def _record_request_failure(self) -> None:
        """Record one failed transport attempt."""
        self._consecutive_failures += 1
        self._is_healthy = False
        if getattr(self, "_circuit", None):
            try:
                self._circuit.record_failure()
            except Exception as exc:
                logger.exception(
                    "Circuit failure metric update failed",
                    exc_info=sanitized_exception_info(exc),
                )

    def _sleep_before_retry(
        self,
        attempt: int,
        *,
        response: httpx.Response | None = None,
    ) -> None:
        """Wait before a retry, honoring Retry-After when the server provides it."""
        retry_after = self._extract_retry_after(response) if response is not None else None
        if retry_after is not None:
            delay = float(retry_after)
        else:
            try:
                retry_backoff = float(self.retry_backoff)
            except (TypeError, ValueError):
                retry_backoff = 0.0
            if not math.isfinite(retry_backoff) or retry_backoff <= 0:
                return
            bounded_attempt = min(max(attempt, 0), 30)
            delay = retry_backoff * (2**bounded_attempt)
        delay = min(delay, self.http_limits.max_retry_delay_seconds)
        if delay > 0:
            time.sleep(delay)

    def _handle_response(
        self, response: httpx.Response, method: str, url: str
    ) -> dict[str, Any] | list[Any] | str | None:
        """Handle the HTTP response."""
        status = response.status_code

        if status >= 400:
            self._record_request_failure()

            if status == 429:
                retry_after = self._extract_retry_after(response)
                logger.error(
                    "API HTTP 429 rate limit for %s %s request",
                    self._get_config_prefix(),
                    method,
                )
                rate_limit_exc = self.get_rate_limit_exception_class()
                raise rate_limit_exc(
                    message=f"Rate limit exceeded for {method} request",
                    retry_after=retry_after,
                    response=response,
                )

            logger.error(
                "API HTTP error for %s %s request: status %s; body redacted",
                self._get_config_prefix(),
                method,
                status,
            )
            api_exc = self.get_exception_class()
            raise api_exc(
                message=f"HTTP error for {method} request; response body redacted",
                status_code=status,
                response=response,
            ) from None

        content = self._bounded_response_content(response, method=method)

        self._last_successful_request = time.time()
        self._consecutive_failures = 0
        self._is_healthy = True

        if getattr(self, "_circuit", None):
            try:
                self._circuit.record_success()
            except Exception as exc:
                logger.exception(
                    "Circuit success metric update failed",
                    exc_info=sanitized_exception_info(exc),
                )

        try:
            result = response.json() if content else None
        except JSONDecodeError as exc:
            self._record_request_failure()
            logger.exception(
                "Failed to parse JSON response for %s %s request; body redacted",
                self._get_config_prefix(),
                method,
                exc_info=sanitized_exception_info(exc),
            )
            api_exc = self.get_exception_class()
            raise api_exc(
                message="Invalid JSON API response; body redacted",
                response=response,
            ) from exc
        logger.debug("Request successful for %s %s", self._get_config_prefix(), method)
        return result

    def _bounded_response_content(self, response: httpx.Response, *, method: str) -> bytes:
        """Reject a vendor response that exceeds the configured JSON byte budget."""
        return self._bounded_transport().response_content(response, method=method)

    def _raise_oversized_response(self, method: str) -> NoReturn:
        """Record and raise one secret-safe oversized-response failure."""
        self._record_request_failure()
        logger.error(
            "API response exceeded the byte limit for %s %s request; body redacted",
            self._get_config_prefix(),
            method,
        )
        api_exc = self.get_exception_class()
        raise api_exc(
            message=f"API response exceeded byte limit for {method} request; body redacted",
            response=None,
        ) from None

    def _extract_retry_after(self, response: httpx.Response) -> int | None:
        return self._bounded_transport().extract_retry_after(response)

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self.client.close()

    def __enter__(self) -> Self:
        """Enter the context manager."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Exit the context manager."""
        self.close()
