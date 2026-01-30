"""Django admin configuration package for micboard.

This package organizes admin classes by functional area:
- receivers: WirelessChassis administration
- channels: RFChannel, WirelessUnit administration
- discovery: DiscoveryCIDR, DiscoveryFQDN, DiscoveryJob administration
- discovery_admin: DiscoveryQueue, DeviceMovementLog administration
- assignments: Performer, PerformerAssignment, Alert, UserAlertPreference administration
- monitoring: Location, MonitoringGroup, Group, Config, DiscoveredDevice administration

Note: Admin classes are auto-discovered by Django and don't need explicit imports here.
Importing them here can cause circular import issues during app initialization.
"""

from __future__ import annotations

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
