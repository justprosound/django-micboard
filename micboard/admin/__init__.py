"""
Django admin configuration package for micboard.

This package organizes admin classes by functional area:
- devices: Receiver, Channel, Transmitter administration
- assignments: DeviceAssignment, Alert, UserAlertPreference administration
- monitoring: Location, MonitoringGroup, Group, Config, DiscoveredDevice administration
"""
from __future__ import annotations

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

__all__ = [
    # Device admins
    "ReceiverAdmin",
    "ChannelAdmin",
    "TransmitterAdmin",
    # Assignment admins
    "DeviceAssignmentAdmin",
    "UserAlertPreferenceAdmin",
    "AlertAdmin",
    # Monitoring admins
    "GroupAdmin",
    "MicboardConfigAdmin",
    "DiscoveredDeviceAdmin",
    "LocationAdmin",
    "MonitoringGroupAdmin",
]
