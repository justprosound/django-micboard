"""Device metadata accessor pattern for manufacturer-agnostic metadata handling.

Provides strategy pattern for accessing manufacturer-specific metadata from
DiscoveredDevice models without hardcoding assumptions about metadata structure.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from micboard.models.discovery.manufacturer import Manufacturer

logger = logging.getLogger(__name__)


class DeviceMetadataAccessor(ABC):
    """Abstract base for accessing manufacturer-specific metadata."""

    def __init__(self, device_data: dict[str, Any] | None = None) -> None:
        """Initialize accessor with device metadata.

        Args:
            device_data: Raw metadata dict from DiscoveredDevice.metadata.
        """
        self.data = device_data or {}

    @abstractmethod
    def get_compatibility_status(self) -> str | None:
        """Get device compatibility status (e.g., COMPATIBLE, INCOMPATIBLE_TOO_OLD)."""
        pass

    @abstractmethod
    def get_device_state(self) -> str | None:
        """Get device state (e.g., DISCOVERED, ONLINE, OFFLINE)."""
        pass

    @abstractmethod
    def get_incompatibility_reason(self) -> str | None:
        """Get human-readable reason if device is incompatible."""
        pass

    @staticmethod
    def get_for(
        manufacturer: Manufacturer | None, device_data: dict[str, Any] | None = None
    ) -> DeviceMetadataAccessor:
        """Factory method to get appropriate accessor for manufacturer.

        Args:
            manufacturer: Manufacturer instance (can be None).
            device_data: Metadata dict from DiscoveredDevice.

        Returns:
            Appropriate DeviceMetadataAccessor subclass instance.
        """
        if not manufacturer:
            return GenericMetadataAccessor(device_data)

        code = manufacturer.code.lower() if hasattr(manufacturer, "code") else ""

        if code == "shure":
            return ShureMetadataAccessor(device_data)
        elif code == "sennheiser":
            return SennheiserMetadataAccessor(device_data)

        # Default for unknown manufacturers
        return GenericMetadataAccessor(device_data)


class GenericMetadataAccessor(DeviceMetadataAccessor):
    """Generic accessor for unknown manufacturers."""

    def get_compatibility_status(self) -> str | None:
        return self.data.get("compatibility")

    def get_device_state(self) -> str | None:
        return self.data.get("state") or self.data.get("device_state")

    def get_incompatibility_reason(self) -> str | None:
        return self.data.get("incompatibility_reason")


class ShureMetadataAccessor(DeviceMetadataAccessor):
    """Accessor for Shure-specific metadata structure."""

    def get_compatibility_status(self) -> str | None:
        """Get Shure compatibility status."""
        return self.data.get("compatibility")

    def get_device_state(self) -> str | None:
        """Get Shure device state."""
        return self.data.get("deviceState")

    def get_incompatibility_reason(self) -> str | None:
        """Get human-readable Shure incompatibility reason."""
        compatibility = self.get_compatibility_status()

        if compatibility == "INCOMPATIBLE_TOO_OLD":
            model = self.data.get("model", "device")
            return (
                f"Device firmware is too old for this API version. "
                f"Upgrade {model} firmware to interact via API."
            )
        elif compatibility == "INCOMPATIBLE_TOO_NEW":
            return (
                "Device firmware is too new for this API version. "
                "Upgrade the API to interact with this device."
            )
        elif compatibility != "COMPATIBLE":
            return f"Device is incompatible with current API version (status: {compatibility})."

        return None

    def get_communication_protocol(self) -> str | None:
        """Get Shure communication protocol name."""
        comm_protocol = self.data.get("communicationProtocol", {})
        if isinstance(comm_protocol, dict):
            return comm_protocol.get("name")
        return None


class SennheiserMetadataAccessor(DeviceMetadataAccessor):
    """Accessor for Sennheiser-specific metadata structure."""

    def get_compatibility_status(self) -> str | None:
        """Get Sennheiser compatibility status."""
        return self.data.get("compatibility_status")

    def get_device_state(self) -> str | None:
        """Get Sennheiser device state."""
        return self.data.get("state") or self.data.get("status")

    def get_incompatibility_reason(self) -> str | None:
        """Get human-readable Sennheiser incompatibility reason."""
        status = self.get_compatibility_status()

        if status == "INCOMPATIBLE":
            api_version = self.data.get("required_api_version")
            if api_version:
                return f"Device requires API version {api_version} or higher."
            return "Device is incompatible with current API version."

        return None

    def get_hardware_version(self) -> str | None:
        """Get Sennheiser hardware version."""
        return self.data.get("hardware_version")

    def get_software_version(self) -> str | None:
        """Get Sennheiser software version."""
        return self.data.get("software_version")
