"""Custom exceptions for django-micboard.

Provides structured error handling with clear error codes and details
for debugging and API responses.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

import httpx


class MicboardError(Exception):
    """Base exception for all micboard errors.

    Provides structured exception handling with error codes and details.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "UNKNOWN_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize exception.

        Args:
            message: Human-readable error message
            code: Machine-readable error code
            details: Additional error context
        """
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        """Return error message with code."""
        return f"[{self.code}] {self.message}"


class ManufacturerNotSupportedError(MicboardError):
    """Raised when manufacturer is not supported."""

    def __init__(self, manufacturer_code: str) -> None:
        """Initialize exception.

        Args:
            manufacturer_code: Unsupported manufacturer code
        """
        super().__init__(
            f"Manufacturer '{manufacturer_code}' is not supported",
            code="MANUFACTURER_NOT_SUPPORTED",
            details={"manufacturer": manufacturer_code},
        )


class HardwareNotFoundError(MicboardError):
    """Raised when hardware is not found."""

    def __init__(self, device_id: str, manufacturer_code: str | None = None) -> None:
        """Initialize exception.

        Args:
            device_id: Hardware identifier not found
            manufacturer_code: Optional manufacturer code for context
        """
        details = {"device_id": device_id}
        if manufacturer_code:
            details["manufacturer"] = manufacturer_code

        message = f"Hardware '{device_id}' not found"
        if manufacturer_code:
            message += f" for manufacturer '{manufacturer_code}'"

        super().__init__(
            message,
            code="HARDWARE_NOT_FOUND",
            details=details,
        )


class HardwareValidationError(MicboardError):
    """Raised when hardware data is invalid."""

    def __init__(self, field: str, message: str) -> None:
        """Initialize exception.

        Args:
            field: Field that failed validation
            message: Validation error message
        """
        super().__init__(
            f"Validation error on {field}: {message}",
            code="HARDWARE_VALIDATION_ERROR",
            details={"field": field, "message": message},
        )


class OrganizationDeviceQuotaExceededError(MicboardError):
    """Raised when a tenant-scoped chassis creation would exceed its quota."""

    def __init__(
        self,
        *,
        organization_id: int,
        max_devices: int,
        current_devices: int,
    ) -> None:
        """Describe the finite organization quota that rejected a new chassis."""
        super().__init__(
            f"Organization {organization_id} has reached its device quota "
            f"({current_devices}/{max_devices})",
            code="ORGANIZATION_DEVICE_QUOTA_EXCEEDED",
            details={
                "organization_id": organization_id,
                "max_devices": max_devices,
                "current_devices": current_devices,
            },
        )


class APIError(MicboardError):
    """Base error for bounded manufacturer API operations."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: httpx.Response | None = None,
        *,
        response_body: str | None = None,
        code: str = "API_ERROR",
    ) -> None:
        """Initialize an API error without reading an untrusted response body.

        Args:
            message: Error message
            status_code: HTTP status code from API
            response: Optional response retained for transport-level handling
            response_body: Explicitly supplied, already-bounded response text
            code: Machine-readable error code
        """
        self.status_code = status_code
        self.response = response
        super().__init__(
            message,
            code=code,
            details={
                "status_code": status_code,
                "response": response_body,
            },
        )


class APIRateLimitError(APIError):
    """Raised when a manufacturer API rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int | None = None,
        response: httpx.Response | None = None,
    ) -> None:
        """Initialize a rate-limit error and parse an integer Retry-After value."""
        self.retry_after = retry_after
        if self.retry_after is None and response is not None:
            retry_after_header = response.headers.get("Retry-After")
            if retry_after_header is not None:
                with suppress(ValueError, TypeError):
                    self.retry_after = int(retry_after_header)
        super().__init__(
            message,
            status_code=429,
            response=response,
            code="API_RATE_LIMIT",
        )


class APIAuthenticationError(APIError):
    """Raised when manufacturer API authentication fails."""

    def __init__(self, message: str = "API authentication failed") -> None:
        """Initialize an authentication error."""
        super().__init__(message, status_code=401, code="API_AUTH_ERROR")


class APITimeoutError(APIError):
    """Raised when a manufacturer API operation times out."""

    def __init__(self, message: str = "API request timed out") -> None:
        """Initialize a timeout error."""
        super().__init__(message, code="API_TIMEOUT")


class LocationNotFoundError(MicboardError):
    """Raised when location is not found."""

    def __init__(self, location_id: int) -> None:
        """Initialize exception.

        Args:
            location_id: Location ID not found
        """
        super().__init__(
            f"Location with ID {location_id} not found",
            code="LOCATION_NOT_FOUND",
            details={"location_id": location_id},
        )


class SettingNotFoundError(MicboardError):
    """Raised when a required setting cannot be resolved."""

    def __init__(self, key: str) -> None:
        """Identify the required setting key that could not be resolved."""
        super().__init__(
            f"Required setting '{key}' not found",
            code="SETTING_NOT_FOUND",
            details={"key": key},
        )


class AdminAuditSetupError(MicboardError):
    """Raised when the live admin cannot be audited safely."""

    def __init__(self, message: str) -> None:
        """Retain one sanitized setup failure message under a stable code."""
        super().__init__(message, code="ADMIN_AUDIT_SETUP_ERROR")


class SubscriptionLeaseLostError(MicboardError):
    """Raised when another worker owns a realtime supervisor lease."""

    def __init__(self) -> None:
        """Use a fixed message that cannot expose cache or worker identifiers."""
        super().__init__(
            "Realtime subscription supervisor lease was lost",
            code="SUBSCRIPTION_LEASE_LOST",
        )


class ServiceError(MicboardError):
    """Raised when service operation fails."""

    def __init__(self, service_name: str, operation: str, message: str) -> None:
        """Initialize exception.

        Args:
            service_name: Name of the service
            operation: Operation that failed
            message: Error message
        """
        super().__init__(
            f"{service_name}.{operation}() failed: {message}",
            code="SERVICE_ERROR",
            details={
                "service": service_name,
                "operation": operation,
            },
        )


class DiscoveryError(MicboardError):
    """Raised when device discovery fails."""

    pass


class LocationAlreadyExistsError(MicboardError):
    """Raised when a location with the given name already exists."""

    pass
