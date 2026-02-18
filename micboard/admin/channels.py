"""Admin configuration for RF channel models (RFChannel, WirelessUnit).

This module provides Django admin interfaces for managing wireless audio RF
channels and field units.
"""

from __future__ import annotations

from django.contrib import admin
from django.db.models import Exists, OuterRef
from django.utils.html import format_html

from micboard.admin.mixins import MicboardModelAdmin
from micboard.models import RFChannel, WirelessUnit


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
        from micboard.models.rf_coordination import FrequencyBand

        qs = super().get_queryset(request)

        # Subquery to check for specific frequency band coverage
        bands = FrequencyBand.objects.filter(
            regulatory_domain=OuterRef("chassis__location__building__regulatory_domain"),
            start_frequency_mhz__lte=OuterRef("frequency"),
            end_frequency_mhz__gte=OuterRef("frequency"),
        ).exclude(band_type="forbidden")

        return qs.annotate(_has_specific_band=Exists(bands))

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

        building = chassis.location.building
        domain = building.regulatory_domain

        if not domain:
            return "ℹ️ No regulatory domain"

        if not obj.frequency:
            return "ℹ️ No frequency"

        # Check if covered by general domain frequency range (already in memory from select_related)
        has_coverage = domain.min_frequency_mhz <= obj.frequency <= domain.max_frequency_mhz

        # Or if covered by any specific frequency band (via annotation)
        if not has_coverage:
            has_coverage = getattr(obj, "_has_specific_band", False)

        needs_update = (obj.resource_state in ("active", "reserved")) and not has_coverage

        if needs_update:
            return format_html(
                '<span style="color: var(--error-fg, red); '
                'font-weight: bold;">⚠️ Missing coverage</span>'
            )

        if has_coverage:
            return format_html(
                '<span style="color: var(--success-fg, green);">✅ OK ({} MHz)</span>',
                obj.frequency,
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
    list_select_related = (
        "base_chassis",
        "manufacturer",
        "base_chassis__location",
        "base_chassis__location__building",
        "base_chassis__location__building__regulatory_domain",
    )

    readonly_fields = (
        "battery_percentage",
        "battery_health_detail_display",
        "updated_at",
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

    @admin.display(
        description="Battery",
        ordering="battery",
    )
    def battery_indicator(self, obj):
        """Display colored battery indicator."""
        pct = obj.battery_percentage
        if pct is None:
            return "Unknown"

        # Battery bar representation
        if pct > 50:
            color = "var(--success-fg, green)"
            icon = "●●●●●"
        elif pct > 25:
            color = "var(--warning-fg, orange)"
            icon = "●●●○○"
        elif pct > 10:
            color = "var(--error-fg, orangered)"
            icon = "●●○○○"
        else:
            color = "var(--error-fg, red)"
            icon = "●○○○○"

        return format_html(
            '<span style="color: {}; font-weight: bold;">{} {}%</span>',
            color,
            icon,
            pct,
        )

    @admin.display(description="Health")
    def battery_health_display(self, obj):
        """Display battery health status with icon."""
        health = obj.get_battery_health()
        icon = obj.get_battery_health_display_icon()

        # Simple color mapping
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
    def battery_health_detail_display(self, obj):
        """Display key battery health metrics."""
        parts = []

        if obj.battery_health:
            parts.append(f"Health: {obj.battery_health}")

        pct = obj.battery_percentage
        if pct is not None:
            parts.append(f"{pct}%")

        if obj.battery_cycles:
            parts.append(f"{obj.battery_cycles} cycles")

        if obj.battery_temperature_c:
            parts.append(f"{obj.battery_temperature_c}°C")

        if obj.battery_runtime:
            parts.append(f"Runtime: {obj.battery_runtime}")

        return " | ".join(parts) if parts else "—"

    @admin.display(description="Regulatory Status")
    def regulatory_status_display(self, obj):
        """Display regulatory coverage status."""
        status = obj.get_regulatory_status()

        if status.get("source") == "no_channel":
            return "ℹ️ No RF channel"

        if not status["operating_frequency_mhz"]:
            return "ℹ️ No frequency"

        if status["needs_update"]:
            return format_html(
                '<span style="color: var(--error-fg, red); font-weight: bold;">⚠️ Missing coverage</span>'
            )

        if status["has_coverage"]:
            return format_html(
                '<span style="color: var(--success-fg, green);">✅ OK ({} MHz)</span>',
                status["operating_frequency_mhz"],
            )

        return "—"
