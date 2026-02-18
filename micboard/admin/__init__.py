"""Django admin configuration package for micboard.

This package organizes admin classes by functional area:
- receivers: WirelessChassis administration
- channels: RFChannel, WirelessUnit administration
- discovery: DiscoveryCIDR, DiscoveryFQDN, DiscoveryJob administration
- discovery_admin: DiscoveryQueue, DeviceMovementLog administration
- assignments: Performer, PerformerAssignment, Alert, UserAlertPreference administration
- monitoring: Location, MonitoringGroup, Group, Config, DiscoveredDevice administration

Note: All admin modules must be imported here to trigger @admin.register() decorators.
Django's autodiscover only looks for admin.py files, not admin/ packages.
"""

from __future__ import annotations

# Import all admin modules to trigger registration
from micboard.admin import (
    assignments,
    channels,
    chargers,
    configuration_and_logging,
    discovery,
    discovery_admin,
    display_wall,
    integrations,
    manufacturers,
    monitoring,
    realtime,
    receivers,
    settings,
    users,
)
