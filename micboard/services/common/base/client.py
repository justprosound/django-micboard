from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
    def add_discovery_ips(self, ips: list[str]) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def remove_discovery_ips(self, ips: list[str]) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def get_discovery_ips(self) -> list[str]:
        raise NotImplementedError()

    @abstractmethod
    def _make_request(self, *args, **kwargs) -> Any:
        raise NotImplementedError()


class BaseHTTPClient(BaseAPIClient, HealthCheckMixin):
    def __init__(self, base_url: str | None = None, verify_ssl: bool | None = None):
        from micboard.services.settings import settings

        config_dict = settings.get_config_dict()
        prefix = self._get_config_prefix()

        self.base_url = (
            base_url
            if base_url is not None
            else config_dict.get(f"{prefix}_BASE_URL", self._get_default_base_url()).rstrip("/")
        )
        self.timeout = config_dict.get(f"{prefix}_TIMEOUT", 10)
        self.verify_ssl = (
            verify_ssl if verify_ssl is not None else config_dict.get(f"{prefix}_VERIFY_SSL", True)
        )

        self.max_retries = config_dict.get(f"{prefix}_MAX_RETRIES", 3)
        self.retry_backoff = config_dict.get(f"{prefix}_RETRY_BACKOFF", 0.5)
        self.retry_status_codes = config_dict.get(
            f"{prefix}_RETRY_STATUS_CODES", [429, 500, 502, 503, 504]
        )

        self._last_successful_request: float | None = None
        self._consecutive_failures = 0
        self._is_healthy = True

        self.session = requests.Session()

        adapter = HTTPAdapter(
            max_retries=self._create_retry_strategy(),
            pool_connections=10,
            pool_maxsize=20,
            pool_block=False,
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        failure_threshold = config_dict.get(f"{prefix}_CIRCUIT_FAILURE_THRESHOLD", 5)
        recovery_timeout = config_dict.get(f"{prefix}_CIRCUIT_RECOVERY_TIMEOUT", 60)
        self._circuit = CircuitBreaker(
            name=prefix, failure_threshold=failure_threshold, recovery_timeout=recovery_timeout
        )

        self._configure_authentication(config_dict)

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

    def _create_retry_strategy(self) -> Retry:
        return Retry(
            total=self.max_retries,
            backoff_factor=self.retry_backoff,
            status_forcelist=self.retry_status_codes,
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
            raise_on_status=False,
        )

    def is_healthy(self) -> bool:
        return self._is_healthy and self._consecutive_failures < 5

    def check_health(self) -> dict[str, Any]:
        try:
            endpoint = self._get_health_check_endpoint()
            response = self.session.get(
                f"{self.base_url}{endpoint}",
                timeout=5,
                verify=self.verify_ssl,
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

        except requests.RequestException as e:
            return self._standardize_health_response(
                status="error",
                error=f"Health check failed: {e}",
            )

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Any | None:
        url = f"{self.base_url}{endpoint}"
        logger.debug("Making %s request to %s", method, url)
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", self.verify_ssl)

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
        status = getattr(response, "status_code", None)

        if status is not None and status >= 400:
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

        self._last_successful_request = time.time()
        self._consecutive_failures = 0
        self._is_healthy = True

        if getattr(self, "_circuit", None):
            try:
                self._circuit.record_success()
            except Exception:
                logger.debug("Circuit record_success failed", exc_info=True)

        result = response.json() if response.content else None
        logger.debug("Request successful: %s %s", method, url)
        return result

    def _extract_retry_after(self, response: requests.Response) -> int | None:
        try:
            retry_after_header = response.headers.get("Retry-After")
            if retry_after_header is not None:
                return int(retry_after_header)
        except ValueError:
            return None
        return None

    def _handle_http_error(self, e: requests.exceptions.HTTPError, method: str, url: str) -> None:
        status_code = getattr(e.response, "status_code", None)
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
            e.response.text[:200],
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
        if getattr(self, "_circuit", None):
            try:
                self._circuit.record_failure()
            except Exception:
                logger.debug("Circuit record_failure failed", exc_info=True)

        self._consecutive_failures += 1
        logger.error("Failed to parse JSON response from %s %s: %s", method, url, e)
        api_exc = self.get_exception_class()
        raise api_exc(f"Invalid JSON response from {url}", response=None) from e
