"""Service functions for DiscoveredDevice business logic.

Provides query and validation functions for discovered device lifecycle,
separated from the model layer per ADR-002.
"""

from __future__ import annotations

import logging

from micboard.models.discovery.registry import DiscoveredDevice
from micboard.services.core.device_metadata import DeviceMetadataAccessor

logger = logging.getLogger(__name__)


def get_device_metadata_accessor(
    device: DiscoveredDevice,
) -> DeviceMetadataAccessor:
    """Get manufacturer-specific metadata accessor for a discovered device."""
    return DeviceMetadataAccessor.get_for(device.manufacturer, device.metadata)


def is_device_manageable(device: DiscoveredDevice) -> bool:
    """Check if device is ready to be managed via API.

    A device is manageable if:
    - Status is 'ready'
    - It has a valid API device ID
    """
    if device.status != DiscoveredDevice.STATUS_READY:
        return False
    if not device.api_device_id:
        return False
    return True


def get_device_incompatibility_reason(device: DiscoveredDevice) -> str | None:
    """Get human-readable reason why device cannot be managed.

    Returns None if device is manageable.
    """
    if device.status == DiscoveredDevice.STATUS_INCOMPATIBLE:
        accessor = get_device_metadata_accessor(device)
        reason = accessor.get_incompatibility_reason()
        if reason:
            return reason
        return "Device is incompatible with current API version."

    elif device.status == DiscoveredDevice.STATUS_PENDING:
        accessor = get_device_metadata_accessor(device)
        device_state = accessor.get_device_state()
        if device_state == "DISCOVERED":
            return (
                "Device is in DISCOVERED state - not yet ready for API interaction. "
                "Wait for device to come ONLINE or check network connectivity."
            )
        return "Device discovered but not yet ready for management."

    elif device.status == DiscoveredDevice.STATUS_ERROR:
        return "Device is in ERROR state. Check device logs and network connectivity."

    elif device.status == DiscoveredDevice.STATUS_OFFLINE:
        return "Device is offline. Check power and network connectivity."

    elif not device.api_device_id:
        return "Device ID not available from API. Cannot establish communication."

    return None


def can_promote_device_to_chassis(device: DiscoveredDevice) -> tuple[bool, str]:
    """Check if device can be promoted to WirelessChassis.

    Returns:
        Tuple of (can_promote: bool, reason: str)
    """
    from micboard.models import WirelessChassis

    if WirelessChassis.objects.filter(ip=device.ip, manufacturer=device.manufacturer).exists():
        return (False, "Device is already managed as WirelessChassis")

    incompatibility_reason = get_device_incompatibility_reason(device)
    if incompatibility_reason:
        return (False, incompatibility_reason)

    if not device.manufacturer:
        return (False, "No manufacturer specified")

    return (True, "Device is ready to be promoted to managed chassis")


def get_device_communication_protocol(device: DiscoveredDevice) -> str | None:
    """Get communication protocol name from metadata."""
    accessor = get_device_metadata_accessor(device)
    if hasattr(accessor, "get_communication_protocol"):
        return accessor.get_communication_protocol()  # type: ignore[return-value]
    return None
