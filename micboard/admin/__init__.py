"""
Django admin configuration package for micboard.

This package organizes admin classes by functional area:
- receivers: Receiver administration
- channels: Channel, Transmitter administration
- discovery: DiscoveryCIDR, DiscoveryFQDN, DiscoveryJob administration
- assignments: DeviceAssignment, Alert, UserAlertPreference administration
- monitoring: Location, MonitoringGroup, Group, Config, DiscoveredDevice administration
"""

from __future__ import annotations

from typing import ClassVar

from .assignments import (
    AlertAdmin,
    DeviceAssignmentAdmin,
    UserAlertPreferenceAdmin,
)
from .channels import ChannelAdmin, TransmitterAdmin
from .discovery import DiscoveryCIDRAdmin, DiscoveryFQDNAdmin, DiscoveryJobAdmin
from .manufacturers import ManufacturerAdmin
from .monitoring import (
    DiscoveredDeviceAdmin,
    GroupAdmin,
    LocationAdmin,
    MicboardConfigAdmin,
    MonitoringGroupAdmin,
)
from .receivers import ReceiverAdmin

__all__ = sorted(
    [
        "AlertAdmin",
        "ChannelAdmin",
        "DeviceAssignmentAdmin",
        "DiscoveryCIDRAdmin",
        "DiscoveryFQDNAdmin",
        "DiscoveryJobAdmin",
        "DiscoveredDeviceAdmin",
        "GroupAdmin",
        "LocationAdmin",
        "MicboardConfigAdmin",
        "MonitoringGroupAdmin",
        "ReceiverAdmin",
        "TransmitterAdmin",
        "UserAlertPreferenceAdmin",
        "ManufacturerAdmin",
    ]
)
