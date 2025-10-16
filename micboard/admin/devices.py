"""
Admin configuration for device models (Receiver, Channel, Transmitter).

This module provides Django admin interfaces for managing wireless audio devices.
"""

from __future__ import annotations

import logging
from typing import ClassVar

from django.contrib import admin
from django.utils.html import format_html

from micboard.models import Channel, Receiver, Transmitter

logger = logging.getLogger(__name__)


class ChannelInline(admin.StackedInline):
    """Inline admin for Channel model."""

    model = Channel
    extra = 1  # Number of empty forms to display
    readonly_fields = ("get_transmitter_status",)

    def get_transmitter_status(self, obj):
        """Show transmitter status in inline."""
        if hasattr(obj, "transmitter"):
            tx = obj.transmitter
            return format_html(
                "<strong>Slot {}:</strong> Battery {}% | Audio {} dB | RF {} dBm",
                tx.slot,
                tx.battery_percentage or "?",
                tx.audio_level,
                tx.rf_level,
            )
        return "No transmitter assigned"

    get_transmitter_status.short_description = "Transmitter Status"  # type: ignore


class TransmitterInline(admin.StackedInline):
    """Inline admin for Transmitter model."""

    model = Transmitter
    extra = 1
    readonly_fields = ("battery_percentage", "updated_at")


@admin.register(Receiver)
class ReceiverAdmin(admin.ModelAdmin):
    """Admin configuration for Receiver model."""

    list_display = (
        "name",
        "device_type",
        "ip",
        "api_device_id",
        "status_indicator",
        "last_seen",
    )
    list_filter = ("device_type", "is_active")
    search_fields = ("name", "ip", "api_device_id")
    inlines: ClassVar[list] = [ChannelInline]
    readonly_fields = ("last_seen",)
    date_hierarchy = "last_seen"
    actions: ClassVar[list[str]] = ["mark_online", "mark_offline", "sync_from_api"]

    def status_indicator(self, obj):
        """Display colored status indicator."""
        if obj.is_active:
            return format_html(
                '<span style="color: green; font-weight: bold;">● Online</span>',
            )
        return format_html(
            '<span style="color: red; font-weight: bold;">● Offline</span>',
        )

    status_indicator.short_description = "Status"  # type: ignore
    status_indicator.admin_order_field = "is_active"  # type: ignore

    @admin.action(description="Mark selected receivers as online")
    def mark_online(self, request, queryset):
        """Mark selected receivers as online."""
        updated = 0
        for receiver in queryset:
            receiver.mark_online()
            updated += 1
        self.message_user(request, f"{updated} receiver(s) marked as online.")

    @admin.action(description="Mark selected receivers as offline")
    def mark_offline(self, request, queryset):
        """Mark selected receivers as offline."""
        updated = 0
        for receiver in queryset:
            receiver.mark_offline()
            updated += 1
        self.message_user(request, f"{updated} receiver(s) marked as offline.")

    @admin.action(description="Sync selected receivers from API")
    def sync_from_api(self, request, queryset):
        """Sync selected receivers from manufacturer API."""
        synced = 0
        for receiver in queryset:
            try:
                plugin_class = receiver.manufacturer.get_plugin_class()
                plugin = plugin_class(receiver.manufacturer)
                device_data = plugin.get_device(receiver.api_device_id)
                if device_data:
                    transformed_data = plugin.transform_device_data(device_data)
                    receiver.name = transformed_data.get("name", receiver.name)
                    receiver.firmware_version = transformed_data.get(
                        "firmware", receiver.firmware_version
                    )
                    receiver.mark_online()
                    synced += 1
            except Exception as e:
                logger.error("Failed to sync %s: %s", receiver.api_device_id, e)
                self.message_user(
                    request,
                    f"Error syncing {receiver.name}: {e}",
                    level="error",
                )
        if synced > 0:
            self.message_user(request, f"{synced} receiver(s) synced from API.")


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    """Admin configuration for Channel model."""

    list_display = ("__str__", "receiver", "channel_number", "has_transmitter")
    list_filter = ("receiver__device_type", "receiver__is_active")
    search_fields = ("receiver__name", "channel_number")
    inlines: ClassVar[list] = [TransmitterInline]

    def has_transmitter(self, obj):
        """Show if channel has transmitter."""
        if hasattr(obj, "transmitter"):
            return format_html(
                '<span style="color: green;">✓ Yes (Slot {})</span>',
                obj.transmitter.slot,
            )
        return format_html('<span style="color: gray;">✗ No</span>')

    has_transmitter.short_description = "Has Transmitter"  # type: ignore


@admin.register(Transmitter)
class TransmitterAdmin(admin.ModelAdmin):
    """Admin configuration for Transmitter model."""

    list_display = (
        "__str__",
        "channel",
        "slot",
        "battery_indicator",
        "audio_level",
        "rf_level",
        "status",
    )
    list_filter = ("channel__receiver__device_type", "status")
    search_fields = ("channel__receiver__name", "slot", "name")
    readonly_fields = ("battery_percentage", "updated_at")

    def battery_indicator(self, obj):
        """Display colored battery indicator."""
        pct = obj.battery_percentage
        if pct is None:
            return format_html('<span style="color: gray;">Unknown</span>')

        if pct > 50:
            color = "green"
            icon = "●●●●●"
        elif pct > 25:
            color = "orange"
            icon = "●●●○○"
        elif pct > 10:
            color = "orangered"
            icon = "●●○○○"
        else:
            color = "red"
            icon = "●○○○○"

        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}%</span>',
            color,
            icon,
            pct,
        )

    battery_indicator.short_description = "Battery"  # type: ignore
    battery_indicator.admin_order_field = "battery"  # type: ignore
