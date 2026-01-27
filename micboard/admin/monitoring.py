"""Admin configuration for monitoring models.

(Location, MonitoringGroup, Config, DiscoveredDevice).

This module provides Django admin interfaces for managing monitoring groups,
locations, and system configuration.
"""

from __future__ import annotations

from django.contrib import admin

from micboard.admin.mixins import MicboardModelAdmin
from micboard.models import DiscoveredDevice, Location, MicboardConfig, MonitoringGroup


@admin.register(MicboardConfig)
class MicboardConfigAdmin(MicboardModelAdmin):
    """Admin configuration for MicboardConfig model."""

    list_display = ("key", "value")
    search_fields = ("key",)


@admin.register(DiscoveredDevice)
class DiscoveredDeviceAdmin(MicboardModelAdmin):
    """Admin configuration for DiscoveredDevice model."""

    list_display = ("ip", "device_type", "channels", "discovered_at")
    list_filter = ("device_type",)
    search_fields = ("ip", "device_type")


@admin.register(Location)
class LocationAdmin(MicboardModelAdmin):
    """Admin configuration for Location model."""

    list_display = ("name", "building", "room")
    list_filter = ("building", "room")
    search_fields = ("name", "building", "room")


@admin.register(MonitoringGroup)
class MonitoringGroupAdmin(MicboardModelAdmin):
    """Admin configuration for MonitoringGroup model."""

    list_display = ("name", "is_active")
    list_filter = ()
    search_fields = ("name", "description")
    filter_horizontal = (
        "users",
        "channels",
    )  # Use filter_horizontal for better UX with many-to-many
