"""
Models for the micboard app.
"""

# Import all models to make them available at the package level
from .assignments import Alert, DeviceAssignment, UserAlertPreference
from .devices import (
    Channel,
    DiscoveredDevice,
    Group,
    Manufacturer,
    MicboardConfig,
    Receiver,
    Transmitter,
)
from .locations import Location, MonitoringGroup

__all__ = [
    "Alert",
    "Channel",
    "DeviceAssignment",
    "DiscoveredDevice",
    "Group",
    "Location",
    "Manufacturer",
    "MicboardConfig",
    "MonitoringGroup",
    "Receiver",
    "Transmitter",
    "UserAlertPreference",
]
