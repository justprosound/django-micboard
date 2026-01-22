"""
Models for the micboard app.
"""

# Import all models to make them available at the package level
from .activity_log import ActivityLog, ServiceSyncLog
from .assignments import Alert, DeviceAssignment, UserAlertPreference
from .channel import Channel
from .charger import Charger, ChargerSlot
from .configuration import ConfigurationAuditLog, ManufacturerConfiguration
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
    "ActivityLog",
    "Alert",
    "Building",
    "Channel",
    "Charger",
    "ChargerSlot",
    "ConfigurationAuditLog",
    "DeviceAssignment",
    "DiscoveredDevice",
    "DiscoveryCIDR",
    "DiscoveryFQDN",
    "DiscoveryJob",
    "Group",
    "Location",
    "Manufacturer",
    "ManufacturerConfiguration",
    "MicboardConfig",
    "MonitoringGroup",
    "MonitoringGroupLocation",
    "RealTimeConnection",
    "Receiver",
    "Room",
    "ServiceSyncLog",
    "Transmitter",
    "TransmitterSample",
    "TransmitterSession",
    "UserAlertPreference",
    "UserProfile",
    "UserView",
]
