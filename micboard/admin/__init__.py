"""Django admin configuration package for micboard.

This package organizes admin classes by functional area:
- receivers: WirelessChassis administration
- channels: RFChannel, WirelessUnit administration
- discovery: DiscoveryCIDR, DiscoveryFQDN, DiscoveryJob administration
- discovery_admin: DiscoveryQueue, DeviceMovementLog administration
- assignments: Performer, PerformerAssignment, Alert, UserAlertPreference administration
- monitoring: Location, MonitoringGroup, Group, Config, DiscoveredDevice administration
"""

from __future__ import annotations

from .assignments import (
    AlertAdmin as AlertAdmin,
)
from .assignments import (
    PerformerAdmin as PerformerAdmin,
)
from .assignments import (
    PerformerAssignmentAdmin as PerformerAssignmentAdmin,
)
from .assignments import (
    UserAlertPreferenceAdmin as UserAlertPreferenceAdmin,
)
from .channels import RFChannelAdmin as RFChannelAdmin
from .channels import WirelessUnitAdmin as WirelessUnitAdmin
from .chargers import ChargerAdmin as ChargerAdmin
from .chargers import ChargerSlotAdmin as ChargerSlotAdmin
from .configuration_and_logging import (
    ActivityLogAdmin as ActivityLogAdmin,
)
from .configuration_and_logging import (
    ConfigurationAuditLogAdmin as ConfigurationAuditLogAdmin,
)
from .configuration_and_logging import (
    ManufacturerConfigurationAdmin as ManufacturerConfigurationAdmin,
)
from .configuration_and_logging import (
    ServiceSyncLogAdmin as ServiceSyncLogAdmin,
)
from .discovery import (
    DiscoveryCIDRAdmin as DiscoveryCIDRAdmin,
)
from .discovery import (
    DiscoveryFQDNAdmin as DiscoveryFQDNAdmin,
)
from .discovery import (
    DiscoveryJobAdmin as DiscoveryJobAdmin,
)
from .discovery_admin import (
    DeviceMovementLogAdmin as DeviceMovementLogAdmin,
)
from .discovery_admin import (
    DiscoveryQueueAdmin as DiscoveryQueueAdmin,
)
from .display_wall import (
    DisplayWallAdmin as DisplayWallAdmin,
)
from .display_wall import (
    WallSectionAdmin as WallSectionAdmin,
)
from .integrations import (
    AccessoryAdmin as AccessoryAdmin,
)
from .integrations import (
    ManufacturerAPIServerAdmin as ManufacturerAPIServerAdmin,
)
from .manufacturers import ManufacturerAdmin as ManufacturerAdmin
from .monitoring import (
    DiscoveredDeviceAdmin as DiscoveredDeviceAdmin,
)
from .monitoring import (
    LocationAdmin as LocationAdmin,
)
from .monitoring import (
    MicboardConfigAdmin as MicboardConfigAdmin,
)
from .monitoring import (
    MonitoringGroupAdmin as MonitoringGroupAdmin,
)
from .receivers import WirelessChassisAdmin as WirelessChassisAdmin

__all__ = [
    "AccessoryAdmin",
    "ActivityLogAdmin",
    "AlertAdmin",
    "ChargerAdmin",
    "ChargerSlotAdmin",
    "ConfigurationAuditLogAdmin",
    "DeviceMovementLogAdmin",
    "DisplayWallAdmin",
    "DiscoveryCIDRAdmin",
    "DiscoveryFQDNAdmin",
    "DiscoveryJobAdmin",
    "DiscoveryQueueAdmin",
    "DiscoveredDeviceAdmin",
    "LocationAdmin",
    "ManufacturerAdmin",
    "ManufacturerAPIServerAdmin",
    "ManufacturerConfigurationAdmin",
    "MicboardConfigAdmin",
    "MonitoringGroupAdmin",
    "PerformerAdmin",
    "PerformerAssignmentAdmin",
    "RFChannelAdmin",
    "WirelessUnitAdmin",
    "WirelessChassisAdmin",
    "WallSectionAdmin",
    "ServiceSyncLogAdmin",
    "UserAlertPreferenceAdmin",
]
