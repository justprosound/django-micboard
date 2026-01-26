"""Exceptions for services layer.

Provides domain-specific exception types for business logic errors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class MicboardServiceError(Exception):
    """Base exception for all service layer errors."""

    pass


class DeviceNotFoundError(MicboardServiceError):
    """Raised when a device cannot be found."""

    def __init__(self, *, device_id: int | str | None = None, message: str | None = None):
        """Initialize with optional device identifier and custom message."""
        self.device_id = device_id
        detail = message or (
            f"Device not found: {device_id}" if device_id is not None else "Device not found"
        )
        super().__init__(detail)


class AssignmentNotFoundError(MicboardServiceError):
    """Raised when an assignment cannot be found."""

    def __init__(
        self,
        *,
        user_id: int | None = None,
        channel_id: int | None = None,
        device_id: int | None = None,
    ):
        """Capture identifiers that contributed to the missing assignment."""
        self.user_id = user_id
        self.channel_id = channel_id
        self.device_id = device_id

        user_detail = f"user {user_id}" if user_id is not None else "user"
        target = None
        if channel_id is not None:
            target = f"channel {channel_id}"
        elif device_id is not None:
            target = f"device {device_id}"
        else:
            target = "assignment"

        super().__init__(f"Assignment not found for {user_detail} and {target}")


class AssignmentAlreadyExistsError(MicboardServiceError):
    """Raised when trying to create a duplicate assignment."""

    def __init__(
        self,
        *,
        user_id: int | None = None,
        channel_id: int | None = None,
        device_id: int | None = None,
    ):
        """Capture identifiers that triggered the duplicate assignment."""
        self.user_id = user_id
        self.channel_id = channel_id
        self.device_id = device_id

        user_detail = f"user {user_id}" if user_id is not None else "user"
        target = None
        if channel_id is not None:
            target = f"channel {channel_id}"
        elif device_id is not None:
            target = f"device {device_id}"
        else:
            target = "assignment"

        super().__init__(f"Assignment already exists for {user_detail} and {target}")


class LocationNotFoundError(MicboardServiceError):
    """Raised when a location cannot be found."""

    def __init__(self, *, location_id: int | str | None = None, name: str | None = None):
        """Include a location identifier or name in the error message."""
        if location_id:
            super().__init__(f"Location not found: {location_id}")
        elif name:
            super().__init__(f"Location not found: {name}")
        else:
            super().__init__("Location not found")


class LocationAlreadyExistsError(MicboardServiceError):
    """Raised when trying to create a location with duplicate name."""

    def __init__(self, *, name: str):
        """Store the conflicting location name."""
        self.name = name
        super().__init__(f"Location already exists: {name}")


class ManufacturerPluginError(MicboardServiceError):
    """Raised when a manufacturer plugin fails."""

    def __init__(self, *, manufacturer_code: str, message: str):
        """Add manufacturer code and message context to the error."""
        self.manufacturer_code = manufacturer_code
        self.message = message
        super().__init__(f"Manufacturer plugin error ({manufacturer_code}): {message}")


class DiscoveryError(MicboardServiceError):
    """Raised when device discovery fails."""

    pass


class ConnectionError(MicboardServiceError):
    """Raised when connection operations fail."""

    pass
