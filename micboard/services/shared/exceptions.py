"""Service layer exceptions for django-micboard."""

from micboard.exceptions import (
    APIError as ConnectionError,
)
from micboard.exceptions import (
    HardwareNotFoundError,
    HardwareValidationError,
    LocationNotFoundError,
    ServiceError,
)
from micboard.exceptions import (
    ManufacturerNotSupportedError as ManufacturerPluginError,
)
from micboard.exceptions import (
    MicboardError as MicboardServiceError,
)


# Placeholders for missing exceptions to fix imports
class DiscoveryError(MicboardServiceError):
    pass


class LocationAlreadyExistsError(MicboardServiceError):
    pass


__all__ = [
    "MicboardServiceError",
    "ConnectionError",
    "HardwareNotFoundError",
    "HardwareValidationError",
    "DiscoveryError",
    "LocationAlreadyExistsError",
    "LocationNotFoundError",
    "ManufacturerPluginError",
    "ServiceError",
]
