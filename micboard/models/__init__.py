# file: micboard/models/__init__.py
"""Django Micboard Models - Unified domain model layer.

Domain-organized model exports organized by business concern:
- hardware: Wireless base stations, field devices, chargers
- rf_coordination: RF channels and communication paths
- locations: Physical locations, buildings, rooms
- monitoring: Monitoring groups, assignments, alerts
- discovery: Device discovery, manufacturers, configuration
- telemetry: Metrics, samples, API health
- realtime: Real-time connection tracking
- audit: Activity logging and service sync records
- users: User profiles and views
"""

from __future__ import annotations

# Audit domain
from .audit import (
    ActivityLog,
    ConfigurationAuditLog,
    ServiceSyncLog,
)

# Discovery domain
from .discovery import (
    DeviceMovementLog,
    DiscoveredDevice,
    Discovery,
    DiscoveryCIDR,
    DiscoveryFQDN,
    DiscoveryJob,
    DiscoveryQueue,
    Manufacturer,
    ManufacturerConfiguration,
    MicboardConfig,
)

# Hardware domain
from .hardware import (
    Charger,
    ChargerManager,
    ChargerQuerySet,
    ChargerSlot,
    WirelessChassis,
    WirelessChassisManager,
    WirelessChassisQuerySet,
    WirelessUnit,
    WirelessUnitManager,
    WirelessUnitQuerySet,
)

# Locations domain
from .locations import (
    Building,
    Location,
    Room,
)

# Monitoring domain
from .monitoring import (
    Alert,
    Assignment,
    DeviceAssignment,
    Group,
    MonitoringGroup,
    UserAlertPreference,
)

# Real-time domain
from .realtime import (
    RealTimeConnection,
)

# RF Coordination domain
from .rf_coordination import (
    ExclusionZone,
    FrequencyBand,
    RegulatoryDomain,
    RFChannel,
    RFChannelManager,
    RFChannelQuerySet,
)

# Telemetry domain
from .telemetry import (
    APIHealthLog,
    TransmitterSample,
    TransmitterSession,
    WirelessUnitSample,
    WirelessUnitSession,
)

# Users domain
from .users import (
    UserProfile,
    UserView,
)

__all__ = [
    # Hardware
    "Charger",
    "ChargerManager",
    "ChargerQuerySet",
    "ChargerSlot",
    "WirelessChassis",
    "WirelessChassisManager",
    "WirelessChassisQuerySet",
    "WirelessUnit",
    "WirelessUnitManager",
    "WirelessUnitQuerySet",
    # RF Coordination
    "RFChannel",
    "RFChannelManager",
    "RFChannelQuerySet",
    "RegulatoryDomain",
    "FrequencyBand",
    "ExclusionZone",
    # Locations
    "Building",
    "Location",
    "Room",
    # Monitoring
    "Alert",
    "Assignment",
    "DeviceAssignment",
    "UserAlertPreference",
    "Group",
    "MonitoringGroup",
    # Discovery
    "DeviceMovementLog",
    "Discovery",
    "DiscoveryCIDR",
    "DiscoveredDevice",
    "DiscoveryFQDN",
    "DiscoveryJob",
    "DiscoveryQueue",
    "Manufacturer",
    "ManufacturerConfiguration",
    "MicboardConfig",
    # Telemetry
    "APIHealthLog",
    "WirelessUnitSample",
    "WirelessUnitSession",
    "TransmitterSample",
    "TransmitterSession",
    # Real-time
    "RealTimeConnection",
    # Audit
    "ActivityLog",
    "ConfigurationAuditLog",
    "ServiceSyncLog",
    # Users
    "UserProfile",
    "UserView",
]
