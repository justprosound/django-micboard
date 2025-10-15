"""
Admin configuration for monitoring models (Location, MonitoringGroup, Group, Config, DiscoveredDevice).

This module provides Django admin interfaces for managing monitoring groups, locations, and system configuration.
"""

from __future__ import annotations

from django.contrib import admin

from micboard.models import DiscoveredDevice, Group, Location, MicboardConfig, MonitoringGroup


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    """Admin configuration for Group model."""

    list_display = ("group_number", "title", "hide_charts")
    search_fields = ("title",)


@admin.register(MicboardConfig)
class MicboardConfigAdmin(admin.ModelAdmin):
    """Admin configuration for MicboardConfig model."""

    list_display = ("key", "value")
    search_fields = ("key",)


@admin.register(DiscoveredDevice)
class DiscoveredDeviceAdmin(admin.ModelAdmin):
    """Admin configuration for DiscoveredDevice model."""

    list_display = ("ip", "device_type", "channels", "discovered_at")
    list_filter = ("device_type",)
    search_fields = ("ip", "device_type")


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    """Admin configuration for Location model."""

    list_display = ("name", "building", "room")
    list_filter = ("building", "room")
    search_fields = ("name", "building", "room")


@admin.register(MonitoringGroup)
class MonitoringGroupAdmin(admin.ModelAdmin):
    """Admin configuration for MonitoringGroup model."""

    list_display = ("name", "location", "is_active")
    list_filter = ("is_active", "location")
    search_fields = ("name", "description")
    filter_horizontal = (
        "users",
        "channels",
    )  # Use filter_horizontal for better UX with many-to-many
