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
from .chargers import ChargerAdmin, ChargerSlotAdmin
from .configuration_and_logging import (
    ActivityLogAdmin,
    ConfigurationAuditLogAdmin,
    ManufacturerConfigurationAdmin,
    ServiceSyncLogAdmin,
)
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
        "ActivityLogAdmin",
        "AlertAdmin",
        "ChannelAdmin",
        "ChargerAdmin",
        "ChargerSlotAdmin",
        "ConfigurationAuditLogAdmin",
        "DeviceAssignmentAdmin",
        "DiscoveryCIDRAdmin",
        "DiscoveryFQDNAdmin",
        "DiscoveryJobAdmin",
        "DiscoveredDeviceAdmin",
        "GroupAdmin",
        "LocationAdmin",
        "ManufacturerAdmin",
        "ManufacturerConfigurationAdmin",
        "MicboardConfigAdmin",
        "MonitoringGroupAdmin",
        "ReceiverAdmin",
        "ServiceSyncLogAdmin",
        "TransmitterAdmin",
        "UserAlertPreferenceAdmin",
    ]
)
