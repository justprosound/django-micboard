from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from json import JSONDecodeError
from typing import Any

import httpx
from httpx import RequestError, TimeoutException

from micboard.services.monitoring.base_health_mixin import HealthCheckMixin

from .circuit_breaker import CircuitBreaker, CircuitOpenError
from .exceptions import APIError, APIRateLimitError

logger = logging.getLogger(__name__)


class BaseAPIClient(ABC):
    @abstractmethod
    def is_healthy(self) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def check_health(self) -> dict[str, Any]:
        raise NotImplementedError()

    @abstractmethod
    def _make_request(self, *args, **kwargs) -> Any:
        raise NotImplementedError()


class BaseHTTPClient(BaseAPIClient, HealthCheckMixin):
    def __init__(self, base_url: str | None = None):
        from micboard.services.settings import settings

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

        if parsed_url.scheme != "https" or not parsed_url.host:
            raise ValueError(f"{prefix}_BASE_URL must be an absolute HTTPS URL")

    @abstractmethod
    def _get_config_prefix(self) -> str:
        raise NotImplementedError()

    @abstractmethod
    def _get_default_base_url(self) -> str:
        raise NotImplementedError()

    @abstractmethod
    def _configure_authentication(self, config: dict[str, Any]) -> None:
        raise NotImplementedError()

    @abstractmethod
    def _get_health_check_endpoint(self) -> str:
        raise NotImplementedError()

    @abstractmethod
    def get_exception_class(self) -> type[APIError]:
        raise NotImplementedError()

    @abstractmethod
    def get_rate_limit_exception_class(self) -> type[APIRateLimitError]:
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
            response = self.client.get(
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

        except RequestError as e:
            logger.exception("Health check request failed for %s", self.base_url)
            return self._standardize_health_response(
                status="error",
                error=f"Health check failed: {e}",
            )

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Any | None:
        url = f"{self.base_url}{endpoint}"
        logger.debug("Making %s request to %s", method, url)
        kwargs.setdefault("timeout", self.timeout)

        if getattr(self, "_circuit", None) and not self._circuit.allow_request():
            logger.error(
                "Circuit open for %s; failing fast for %s %s",
                self._get_config_prefix(),
                method,
                url,
            )
            raise CircuitOpenError(f"Circuit open for {self._get_config_prefix()}")

        retry_strategy = self._create_retry_strategy()
        max_retries = retry_strategy["total"]
        retry_status_codes = set(retry_strategy["status_forcelist"])

        for attempt in range(max_retries + 1):
            try:
                response = self.client.request(method, url, **kwargs)
            except RequestError as exc:
                self._record_request_failure()
                if attempt < max_retries:
                    logger.exception(
                        "API request failed; retrying attempt %d/%d: %s %s",
                        attempt + 1,
                        max_retries,
                        method,
                        url,
                    )
                    self._sleep_before_retry(attempt)
                    continue

                api_exc = self.get_exception_class()
                if isinstance(exc, TimeoutException):
                    logger.exception("API timeout error: %s %s", method, url)
                    raise api_exc(f"Timeout error for {url}", response=None) from exc

                logger.exception("API connection error: %s %s", method, url)
                raise api_exc(f"Connection error to {url}", response=None) from exc
            except Exception as exc:
                self._record_request_failure()
                logger.exception("API request failed: %s %s", method, url)
                api_exc = self.get_exception_class()
                raise api_exc(f"Unknown request error for {url}", response=None) from exc

            if response.status_code in retry_status_codes and attempt < max_retries:
                self._record_request_failure()
                self._sleep_before_retry(attempt, response=response)
                continue

            # Keep response handling outside the request exception block. This preserves
            # canonical API/rate-limit exceptions raised by `_handle_response`.
            return self._handle_response(response, method, url)

        raise RuntimeError("HTTP retry loop exited without returning or raising")

    def _record_request_failure(self) -> None:
        """Record one failed transport attempt."""
        self._consecutive_failures += 1
        self._is_healthy = False
        if getattr(self, "_circuit", None):
            try:
                self._circuit.record_failure()
            except Exception:
                logger.exception("Circuit record_failure failed")

    def _sleep_before_retry(
        self,
        attempt: int,
        *,
        response: httpx.Response | None = None,
    ) -> None:
        """Wait before a retry, honoring Retry-After when the server provides it."""
        retry_after = self._extract_retry_after(response) if response is not None else None
        delay = float(retry_after) if retry_after is not None else self.retry_backoff * (2**attempt)
        if delay > 0:
            time.sleep(delay)

    def _handle_response(self, response: httpx.Response, method: str, url: str) -> Any | None:
        status = response.status_code

        if status >= 400:
            self._record_request_failure()

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
                response.text[:200],
            )
            api_exc = self.get_exception_class()
            raise api_exc(
                message=f"HTTP error for {method} {url}",
                status_code=status,
                response=response,
            ) from None

        self._last_successful_request = time.time()
        self._consecutive_failures = 0
        self._is_healthy = True

        if getattr(self, "_circuit", None):
            try:
                self._circuit.record_success()
            except Exception:
                logger.exception("Circuit record_success failed")

        try:
            result = response.json() if response.content else None
        except JSONDecodeError as exc:
            self._record_request_failure()
            logger.exception("Failed to parse JSON response from %s %s", method, url)
            api_exc = self.get_exception_class()
            raise api_exc(
                message=f"Invalid JSON response from {url}",
                response=response,
            ) from exc
        logger.debug("Request successful: %s %s", method, url)
        return result

    def _extract_retry_after(self, response: httpx.Response) -> int | None:
        try:
            retry_after_header = response.headers.get("Retry-After")
            if retry_after_header is not None:
                return int(retry_after_header)
        except ValueError:
            logger.exception("Invalid Retry-After header in API response")
            return None
        return None

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self.client.close()

    def __enter__(self) -> BaseHTTPClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
