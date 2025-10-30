"""
Models for the micboard app.
"""

# Import all models to make them available at the package level
from .assignments import Alert, DeviceAssignment, UserAlertPreference
from .channel import Channel
from .charger import Charger, ChargerSlot
from .discovery import (
    DiscoveredDevice,
    DiscoveryCIDR,
    DiscoveryFQDN,
    DiscoveryJob,
    Manufacturer,
    MicboardConfig,
)
from .groups import Group
from .locations import Building, Location, MonitoringGroup, MonitoringGroupLocation, Room
from .realtime import RealTimeConnection
from .receiver import Receiver
from .telemetry import APIHealthLog, TransmitterSample, TransmitterSession
from .transmitter import Transmitter
from .user_profile import UserProfile
from .user_views import UserView

__all__ = [
    "APIHealthLog",
    "Alert",
    "Building",
    "Channel",
    "Charger",
    "ChargerSlot",
    "DeviceAssignment",
    "DiscoveredDevice",
    "DiscoveryCIDR",
    "DiscoveryFQDN",
    "DiscoveryJob",
    "Group",
    "Location",
    "Manufacturer",
    "MicboardConfig",
    "MonitoringGroup",
    "MonitoringGroupLocation",
    "RealTimeConnection",
    "Receiver",
    "Room",
    "Transmitter",
    "TransmitterSample",
    "TransmitterSession",
    "UserAlertPreference",
    "UserProfile",
    "UserView",
]
