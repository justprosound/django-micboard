"""Admin configuration for RF channel models (RFChannel, WirelessUnit).

This module provides Django admin interfaces for managing wireless audio RF
channels and field units.
"""

from __future__ import annotations

from django.contrib import admin
from django.db.models import Exists, OuterRef, Prefetch
from django.utils.html import format_html

from micboard.admin.channel_forms import RFChannelAdminForm, WirelessUnitAdminForm
from micboard.admin.mixins import MicboardModelAdmin
from micboard.admin.regulatory_annotations import (
    regulatory_domain_from_annotations,
    with_regulatory_domain,
)
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.rf_coordination.compliance import FrequencyBand
from micboard.models.rf_coordination.rf_channel import RFChannel
from micboard.services.hardware.rf_channel_service import (
    get_regulatory_status_for_domain as get_rf_channel_regulatory_status,
)
from micboard.services.hardware.wireless_unit_service import (
    get_battery_health,
    get_battery_health_display_icon,
    get_battery_percentage,
    get_regulatory_status_for_domain,
)


@admin.register(RFChannel)
class RFChannelAdmin(MicboardModelAdmin):
    """Admin configuration for RFChannel model."""

    list_display = (
        "__str__",
        "chassis",
        "channel_number",
        "link_direction",
        "active_unit",
        "regulatory_status_optimized",
    )
    list_filter = ("link_direction", "resource_state", "chassis__role")
    search_fields = ("chassis__name", "channel_number", "frequency")
    readonly_fields = ("resource_state",)
    form = RFChannelAdminForm
    list_select_related = (
        "chassis",
        "chassis__manufacturer",
        "active_wireless_unit",
        "active_iem_receiver",
        "chassis__location",
        "chassis__location__building",
        "chassis__location__building__regulatory_domain",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        # Subquery to check for specific frequency band coverage
        bands = FrequencyBand.objects.filter(
            regulatory_domain=OuterRef("chassis__location__building__regulatory_domain"),
            start_frequency_mhz__lte=OuterRef("frequency"),
            end_frequency_mhz__gte=OuterRef("frequency"),
        ).exclude(band_type="forbidden")

        queryset = qs.annotate(_has_specific_band=Exists(bands))
        return with_regulatory_domain(
            queryset,
            building_path="chassis__location__building",
        )

    @admin.display(description="Active Unit")
    def active_unit(self, obj):
        """Show active wireless unit if present."""
        if obj.active_wireless_unit:
            return f"✓ {obj.active_wireless_unit.name} (Slot {obj.active_wireless_unit.slot})"
        return "✗ None"

    @admin.display(description="Regulatory Status")
    def regulatory_status_optimized(self, obj):
        """Optimized regulatory status display using annotated values."""
        # We still need some basic logic, but we avoid the N+1 DB calls
        # because the necessary objects are in select_related/prefetch_related

        chassis = obj.chassis
        if not chassis or not chassis.location or not chassis.location.building:
            return "—"

        if not obj.frequency:
            return "[i] No frequency"

        status = get_rf_channel_regulatory_status(
            obj,
            regulatory_domain_from_annotations(obj),
        )

        if not status["regulatory_domain"]:
            return "[i] No regulatory domain"

        if status["needs_update"]:
            return format_html(
                '<span style="color: var(--error-fg, red); font-weight: bold;">{}</span>',
                "⚠️ Missing coverage",
            )

        if status["has_coverage"]:
            return format_html(
                '<span style="color: var(--success-fg, green);">✅ OK ({} MHz)</span>',
                status["operating_frequency_mhz"],
            )

        return "—"


@admin.register(WirelessUnit)
class WirelessUnitAdmin(MicboardModelAdmin):
    """Admin configuration for WirelessUnit (field device) model."""

    list_display = (
        "__str__",
        "base_chassis",
        "device_type",
        "battery_indicator",
        "battery_health_display",
        "status",
        "regulatory_status_display",
    )
    list_filter = ("device_type", "status", "base_chassis__role")
    search_fields = ("base_chassis__name", "serial_number", "name")
    form = WirelessUnitAdminForm
    list_select_related = (
        "base_chassis",
        "manufacturer",
        "assigned_resource",
        "assigned_resource__chassis",
        "assigned_resource__chassis__location",
        "assigned_resource__chassis__location__building",
        "assigned_resource__chassis__location__building__regulatory_domain",
        "base_chassis__location",
        "base_chassis__location__building",
        "base_chassis__location__building__regulatory_domain",
    )

    readonly_fields = (
        "battery_percentage",
        "battery_health_detail_display",
        "updated_at",
    )

    def get_queryset(self, request):
        """Eager-load the effective RF channel used by regulatory displays."""
        active_channels = RFChannel.objects.select_related(
            "chassis__location__building__regulatory_domain"
        ).order_by("channel_number")
        queryset = (
            super()
            .get_queryset(request)
            .prefetch_related(
                Prefetch(
                    "active_on_receive_channels",
                    queryset=active_channels,
                    to_attr="_admin_active_receive_channels",
                )
            )
        )
        return with_regulatory_domain(
            queryset,
            building_path="base_chassis__location__building",
        )

    fieldsets = (
        (
            "Device Information",
            {
                "fields": (
                    "base_chassis",
                    "device_type",
                    "manufacturer",
                    "model",
                    "serial_number",
                    "name",
                    "slot",
                )
            },
        ),
        (
            "Battery Status",
            {
                "fields": (
                    "battery",
                    "battery_charge",
                    "battery_percentage",
                    "battery_runtime",
                    "battery_type",
                    "battery_health",
                    "battery_cycles",
                    "battery_temperature_c",
                    "battery_health_detail_display",
                ),
                "description": (
                    "Battery level, health, and diagnostic information from manufacturer API."
                ),
            },
        ),
        (
            "RF & Audio",
            {
                "fields": (
                    "assigned_resource",
                    "frequency",
                    "audio_level",
                    "rf_level",
                    "quality",
                    "antenna",
                    "tx_offset",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Status & Metadata",
            {
                "fields": (
                    "status",
                    "api_status",
                    "charging_status",
                    "is_muted",
                    "last_seen",
                    "updated_at",
                    "firmware_version",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Battery", ordering="battery")
    def battery_indicator(self, obj: WirelessUnit) -> str:
        """Display colored battery indicator."""
        percentage = get_battery_percentage(obj)
        if percentage is None:
            return "Unknown"

        if percentage > 50:
            color = "var(--success-fg, green)"
            icon = "●●●●●"
        elif percentage > 25:
            color = "var(--warning-fg, orange)"
            icon = "●●●○○"
        elif percentage > 10:
            color = "var(--error-fg, orangered)"
            icon = "●●○○○"
        else:
            color = "var(--error-fg, red)"
            icon = "●○○○○"

        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}%</span>',
            color,
            icon,
            percentage,
        )

    @admin.display(description="Battery Percentage", ordering="battery")
    def battery_percentage(self, obj: WirelessUnit) -> int | None:
        """Expose normalized battery percentage as an admin-only readonly field."""
        return get_battery_percentage(obj)

    @admin.display(description="Health")
    def battery_health_display(self, obj: WirelessUnit) -> str:
        """Display battery health status with icon."""
        health = get_battery_health(obj)
        icon = get_battery_health_display_icon(obj)
        color_map = {
            "excellent": "var(--success-fg, green)",
            "good": "var(--success-fg, green)",
            "fair": "var(--warning-fg, orange)",
            "poor": "var(--error-fg, orangered)",
            "critical": "var(--error-fg, red)",
        }
        color = color_map.get(health, "var(--body-quiet-color, gray)")
        return format_html(
            '<span style="color: {};">{} {}</span>',
            color,
            icon,
            health.title(),
        )

    @admin.display(description="Battery Details")
    def battery_health_detail_display(self, obj: WirelessUnit) -> str:
        """Display key battery health metrics."""
        parts = []
        if obj.battery_health:
            parts.append(f"Health: {obj.battery_health}")

        percentage = get_battery_percentage(obj)
        if percentage is not None:
            parts.append(f"{percentage}%")
        if obj.battery_cycles:
            parts.append(f"{obj.battery_cycles} cycles")
        if obj.battery_temperature_c:
            parts.append(f"{obj.battery_temperature_c}°C")
        if obj.battery_runtime:
            parts.append(f"Runtime: {obj.battery_runtime}")
        return " | ".join(parts) if parts else "—"

    @admin.display(description="Regulatory Status")
    def regulatory_status_display(self, obj: WirelessUnit) -> str:
        """Display regulatory coverage status."""
        status = get_regulatory_status_for_domain(
            obj,
            regulatory_domain_from_annotations(obj),
        )
        if status.get("source") == "no_channel":
            return "[i] No RF channel"
        if not status["operating_frequency_mhz"]:
            return "[i] No frequency"
        if status["needs_update"]:
            return format_html(
                '<span style="color: var(--error-fg, red); font-weight: bold;">{}</span>',
                "⚠️ Missing coverage",
            )
        if status["has_coverage"]:
            return format_html(
                '<span style="color: var(--success-fg, green);">✅ OK ({} MHz)</span>',
                status["operating_frequency_mhz"],
            )
        return "—"
