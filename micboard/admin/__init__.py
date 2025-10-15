"""
Django admin configuration package for micboard.

This package organizes admin classes by functional area:
- devices: Receiver, Channel, Transmitter administration
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
from .devices import ChannelAdmin, ReceiverAdmin, TransmitterAdmin
from .monitoring import (
    DiscoveredDeviceAdmin,
    GroupAdmin,
    LocationAdmin,
    MicboardConfigAdmin,
    MonitoringGroupAdmin,
)

__all__ = sorted(
    [
        "AlertAdmin",
        "ChannelAdmin",
        "DeviceAssignmentAdmin",
        "DiscoveredDeviceAdmin",
        "GroupAdmin",
        "LocationAdmin",
        "MicboardConfigAdmin",
        "MonitoringGroupAdmin",
        "ReceiverAdmin",
        "TransmitterAdmin",
        "UserAlertPreferenceAdmin",
    ]
)
