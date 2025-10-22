"""
Admin configuration for channel models (Channel, Transmitter).

This module provides Django admin interfaces for managing wireless audio channels and transmitters.
"""

from __future__ import annotations

from typing import ClassVar

from django.contrib import admin
from django.utils.html import format_html

from micboard.models import Channel, Transmitter


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    """Admin configuration for Channel model."""

    list_display = ("__str__", "receiver", "channel_number", "has_transmitter")
    list_filter = ("receiver__device_type", "receiver__is_active")
    search_fields = ("receiver__name", "channel_number")
    inlines: ClassVar[list] = []  # Removed TransmitterInline to avoid duplication

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
