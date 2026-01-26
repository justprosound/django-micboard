"""Admin configuration for RF channel models (RFChannel, WirelessUnit).

This module provides Django admin interfaces for managing wireless audio RF
channels and field units.
"""

from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from micboard.models import RFChannel, WirelessUnit


@admin.register(RFChannel)
class RFChannelAdmin(admin.ModelAdmin):
    """Admin configuration for RFChannel model."""

    list_display = (
        "__str__",
        "chassis",
        "channel_number",
        "link_direction",
        "active_unit",
        "regulatory_status_display",
    )
    list_filter = ("link_direction", "resource_state", "chassis__role")
    search_fields = ("chassis__name", "channel_number", "frequency")
    readonly_fields = ("resource_state",)

    @admin.display(description="Active Unit")
    def active_unit(self, obj):
        """Show active wireless unit if present."""
        if obj.active_wireless_unit:
            return format_html(
                '<span style="color: green;">✓ {} (Slot {})</span>',
                obj.active_wireless_unit.name,
                obj.active_wireless_unit.slot,
            )
        return format_html('<span style="color: gray;">✗ None</span>')

    @admin.display(description="Regulatory Status")
    def regulatory_status_display(self, obj):
        """Display regulatory coverage status with color coding."""
        status = obj.get_regulatory_status()

        if not status["operating_frequency_mhz"]:
            return format_html('<span style="color: gray;">ℹ️ No frequency</span>')

        if status["needs_update"]:
            return format_html(
                '<span style="color: red; font-weight: bold;">⚠️ Missing coverage</span>'
            )

        if status["has_coverage"]:
            return format_html(
                '<span style="color: green;">✅ OK ({} MHz)</span>',
                status["operating_frequency_mhz"],
            )

        return format_html('<span style="color: gray;">—</span>')


@admin.register(WirelessUnit)
class WirelessUnitAdmin(admin.ModelAdmin):
    """Admin configuration for WirelessUnit (field device) model."""

    list_display = (
        "__str__",
        "base_chassis",
        "device_type",
        "battery_indicator",
        "status",
        "regulatory_status_display",
    )
    list_filter = ("device_type", "status", "base_chassis__role")
    search_fields = ("base_chassis__name", "serial_number", "name")

    readonly_fields = ("battery_percentage", "updated_at")

    @admin.display(
        description="Battery",
        ordering="battery",
    )
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

    @admin.display(description="Regulatory Status")
    def regulatory_status_display(self, obj):
        """Display regulatory coverage status (delegates to RFChannel).

        Note: RF coordination happens at RFChannel level.
        This display delegates to the assigned channel's regulatory status.
        """
        status = obj.get_regulatory_status()

        # No RF channel assigned
        if status.get("source") == "no_channel":
            return format_html('<span style="color: gray;">ℹ️ No RF channel</span>')

        if not status["operating_frequency_mhz"]:
            return format_html('<span style="color: gray;">ℹ️ No frequency</span>')

        if status["needs_update"]:
            return format_html(
                '<span style="color: red; font-weight: bold;">⚠️ Missing coverage</span>'
            )

        if status["has_coverage"]:
            return format_html(
                '<span style="color: green;">✅ OK ({} MHz)</span>',
                status["operating_frequency_mhz"],
            )

        return format_html('<span style="color: gray;">—</span>')
