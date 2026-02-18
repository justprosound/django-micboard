"""Django Micboard Models package.

This module re-exports commonly used models for convenience.
Models are organized by domain in submodules.
"""

# Import submodules for Django app registry
from . import (
    audit,  # noqa: F401
    discovery,  # noqa: F401
    hardware,  # noqa: F401
    integrations,  # noqa: F401
    locations,  # noqa: F401
    monitoring,  # noqa: F401
    multitenancy,  # noqa: F401
    realtime,  # noqa: F401
    rf_coordination,  # noqa: F401
    settings,  # noqa: F401
    telemetry,  # noqa: F401
    users,  # noqa: F401
)

# Re-export commonly used models for backward compatibility
# Audit models
from .audit import ActivityLog, ConfigurationAuditLog, ServiceSyncLog

# Discovery models
from .discovery.configuration import ManufacturerConfiguration
from .discovery.manufacturer import Manufacturer

# Telemetry
from .discovery.queue import DeviceMovementLog, DiscoveryQueue
from .discovery.registry import (
    DiscoveredDevice,
    DiscoveryCIDR,
    DiscoveryFQDN,
    DiscoveryJob,
    MicboardConfig,
)

# Hardware models
from .hardware.charger import Charger, ChargerSlot
from .hardware.display_wall import DisplayWall, WallSection
from .hardware.wireless_chassis import WirelessChassis
from .hardware.wireless_unit import WirelessUnit

# Integrations
from .integrations import ManufacturerAPIServer

# Location models
from .locations import Building, Location, Room

# Monitoring models
from .monitoring.alert import Alert, UserAlertPreference
from .monitoring.group import MonitoringGroup
from .monitoring.performer import Performer
from .monitoring.performer_assignment import PerformerAssignment

# Realtime models
from .realtime.connection import RealTimeConnection

# RF Coordination models
from .rf_coordination.compliance import ExclusionZone, FrequencyBand, RegulatoryDomain
from .rf_coordination.rf_channel import RFChannel

# Settings models
from .settings import Setting, SettingDefinition

# User models
from .users.user_profile import UserProfile
from .users.user_views import UserView

__all__ = [
    # Audit
    "ActivityLog",
    "ConfigurationAuditLog",
    "ServiceSyncLog",
    # Discovery
    "DiscoveredDevice",
    "DiscoveryCIDR",
    "DiscoveryFQDN",
    "DiscoveryJob",
    "DiscoveryQueue",
    "Manufacturer",
    "ManufacturerConfiguration",
    "MicboardConfig",
    # Hardware
    "Charger",
    "ChargerSlot",
    "DisplayWall",
    "WallSection",
    "WirelessChassis",
    "WirelessUnit",
    # Location
    "Building",
    "Location",
    "Room",
    # Monitoring
    "Alert",
    "MonitoringGroup",
    "Performer",
    "PerformerAssignment",
    "UserAlertPreference",
    # Realtime
    "RealTimeConnection",
    # RF Coordination
    "ExclusionZone",
    "FrequencyBand",
    "RegulatoryDomain",
    "RFChannel",
    # Settings
    "Setting",
    "SettingDefinition",
    # Users
    "UserProfile",
    "UserView",
    # Telemetry
    "DeviceMovementLog",
]
