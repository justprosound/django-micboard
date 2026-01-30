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
- settings: Configuration and settings management
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
    DisplayWall,
    WallSection,
    WirelessChassis,
    WirelessChassisManager,
    WirelessChassisQuerySet,
    WirelessUnit,
    WirelessUnitManager,
    WirelessUnitQuerySet,
)

# Integration domain
from .integrations import (
    Accessory,
    ManufacturerAPIServer,
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
    MonitoringGroup,
    Performer,
    PerformerAssignment,
    UserAlertPreference,
)

# Multi-tenancy domain
from .multitenancy import (
    Organization,
    Site,
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

# Settings domain
from .settings import (
    Setting,
    SettingDefinition,
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
    "DisplayWall",
    "WallSection",
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
    # Multi-tenancy
    "Organization",
    "Site",
    # Monitoring
    "Alert",
    "UserAlertPreference",
    "MonitoringGroup",
    "Performer",
    "PerformerAssignment",
    # Discovery
    "DeviceMovementLog",
    "DiscoveredDevice",
    "DiscoveryCIDR",
    "DiscoveryFQDN",
    "DiscoveryJob",
    "DiscoveryQueue",
    "Manufacturer",
    "ManufacturerConfiguration",
    "MicboardConfig",
    # Settings
    "Setting",
    "SettingDefinition",
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
    # Integrations
    "ManufacturerAPIServer",
    "Accessory",
]
