"""Custom exceptions for django-micboard.

Provides structured error handling with clear error codes and details
for debugging and API responses.
"""

from __future__ import annotations

from typing import Any


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
    ):
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

    def __init__(self, manufacturer_code: str):
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

    def __init__(self, device_id: str, manufacturer_code: str | None = None):
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

    def __init__(self, field: str, message: str):
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


class APIError(MicboardError):
    """Raised when manufacturer API call fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str | None = None,
    ):
        """Initialize exception.

        Args:
            message: Error message
            status_code: HTTP status code from API
            response_body: Response body from API
        """
        super().__init__(
            message,
            code="API_ERROR",
            details={
                "status_code": status_code,
                "response": response_body,
            },
        )


class LocationNotFoundError(MicboardError):
    """Raised when location is not found."""

    def __init__(self, location_id: int):
        """Initialize exception.

        Args:
            location_id: Location ID not found
        """
        super().__init__(
            f"Location with ID {location_id} not found",
            code="LOCATION_NOT_FOUND",
            details={"location_id": location_id},
        )


class ServiceError(MicboardError):
    """Raised when service operation fails."""

    def __init__(self, service_name: str, operation: str, message: str):
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
