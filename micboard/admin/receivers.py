"""Admin configuration for wireless chassis and units.

This module provides Django admin interfaces for managing wireless audio hardware.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from django.contrib import admin
from django.db.models import Count, Q
from django.shortcuts import render
from django.urls import path
from django.utils.html import format_html

from micboard.admin.forms import WirelessChassisAdminForm
from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.hardware.accessory import Accessory
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.rf_coordination.rf_channel import RFChannel

logger = logging.getLogger(__name__)


class WirelessUnitInline(admin.StackedInline):
    """Inline admin for WirelessUnit model."""

    model = WirelessUnit
    fk_name = "base_chassis"
    extra = 0
    readonly_fields = (
        "battery_percentage",
        "updated_at",
        "device_type",
        "name",
        "status",
    )
    fields = (
        "device_type",
        "name",
        "battery_percentage",
        "audio_level",
        "rf_level",
        "status",
        "updated_at",
    )
    can_delete = False


class RFChannelInline(admin.StackedInline):
    """Inline admin for RFChannel model."""

    model = RFChannel
    fk_name = "chassis"


class AccessoryInline(admin.TabularInline):
    """Inline admin for managing accessories attached to a chassis."""

    model = Accessory
    extra = 1
    fields = (
        "category",
        "name",
        "assigned_to",
        "condition",
        "is_available",
        "checked_out_date",
    )
    readonly_fields = ("created_at",)


@admin.register(WirelessChassis)
class WirelessChassisAdmin(MicboardModelAdmin):
    """Admin configuration for WirelessChassis model."""

    form = WirelessChassisAdminForm
    list_display = (
        "name",
        "role",
        "manufacturer_display",
        "ip",
        "api_device_id",
        "status_indicator",
        "band_plan_display",
        "band_plan_regulatory_status_display",
        "channel_count_display",
        "active_units_display",
        "last_seen",
    )
    list_filter = ("role", "status", "manufacturer")
    search_fields = ("name", "ip", "api_device_id")
    list_select_related = ("manufacturer", "location")
    inlines: ClassVar[list] = [RFChannelInline, AccessoryInline]
    readonly_fields = ("last_seen", "get_hardware_summary")
    date_hierarchy = "last_seen"
    actions: ClassVar[list[str]] = ["mark_online", "mark_offline", "sync_from_api"]

    def save_model(self, request, obj, form, change):
        """Delegate all business logic to HardwareService."""
        from micboard.services.core.hardware import HardwareService

        super().save_model(request, obj, form, change)
        HardwareService.handle_chassis_save(chassis=obj, created=not change)

    def delete_model(self, request, obj):
        """Delegate all business logic to HardwareService."""
        from micboard.services.core.hardware import HardwareService

        HardwareService.handle_chassis_delete(chassis=obj)
        super().delete_model(request, obj)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                _channel_count=Count("rf_channels", distinct=True),
                _active_units_count=Count(
                    "rf_channels",
                    filter=Q(rf_channels__active_wireless_unit__isnull=False)
                    | Q(rf_channels__active_iem_receiver__isnull=False),
                    distinct=True,
                ),
            )
        )

    @admin.display(description="Channels", ordering="_channel_count")
    def channel_count_display(self, obj):
        return getattr(obj, "_channel_count", 0)

    @admin.display(description="Active Units", ordering="_active_units_count")
    def active_units_display(self, obj):
        return getattr(obj, "_active_units_count", 0)

    fieldsets = (
        (
            "Hardware Identity",
            {
                "fields": (
                    "role",
                    "manufacturer",
                    "model",
                    "name",
                    "api_device_id",
                    "serial_number",
                    "mac_address",
                )
            },
        ),
        (
            "Band Plan Configuration",
            {
                "fields": (
                    "band_plan_selector",
                    "band_plan_name",
                    "band_plan_min_mhz",
                    "band_plan_max_mhz",
                ),
                "description": (
                    "Configure the frequency range this chassis operates on. "
                    "Select from standard band plans for automatic frequency population."
                ),
            },
        ),
        (
            "Network Configuration",
            {
                "fields": (
                    "ip",
                    "subnet_mask",
                    "gateway",
                    "network_mode",
                    "interface_id",
                    "mac_address_secondary",
                    "ip_address_secondary",
                )
            },
        ),
        (
            "Status & Location",
            {
                "fields": (
                    "status",
                    "location",
                    "order",
                    "last_seen",
                )
            },
        ),
        (
            "Hardware Capabilities",
            {
                "fields": (
                    "max_channels",
                    "dante_capable",
                    "protocol_family",
                    "wmas_capable",
                    "licensed_resource_count",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Firmware & Hardware Details",
            {
                "fields": (
                    "firmware_version",
                    "hosted_firmware_version",
                    "get_hardware_summary",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "hardware-layout/",
                self.admin_site.admin_view(self.hardware_layout_view),
                name="micboard_wireless_chassis_hardware_layout",
            ),
        ]
        return custom_urls + urls

    def hardware_layout_view(self, request):
        """Custom view showing hardware layout for all wireless chassis.

        Build a compact structure grouped by manufacturer and chassis IP, then
        for each chassis list channels with their current frequency (if any).
        """
        chassis_qs = (
            WirelessChassis.objects.filter(status__in=["online", "degraded", "provisioning"])
            .select_related("manufacturer")
            .prefetch_related(
                "rf_channels__active_wireless_unit",
                "rf_channels__active_iem_receiver",
            )
            .annotate(
                channel_count=Count("rf_channels"),
                unit_count=Count(
                    "rf_channels",
                    filter=Q(rf_channels__active_wireless_unit__isnull=False),
                ),
            )
            .order_by("manufacturer__name", "ip")
        )

        # Build grouped structure for template to avoid complex template logic
        grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for chassis in chassis_qs:
            m_name = chassis.manufacturer.name if chassis.manufacturer else "Unknown"
            grouped.setdefault(m_name, {})
            # Use IP as chassis location identifier
            loc = chassis.ip or "Unknown IP"
            grouped[m_name].setdefault(loc, [])

            channels = []
            for ch in chassis.rf_channels.all().order_by("channel_number"):
                freq = None
                unit = ch.active_wireless_unit or ch.active_iem_receiver
                if unit and getattr(unit, "frequency", None):
                    freq = unit.frequency
                channels.append({"channel_number": ch.channel_number, "frequency": freq})

            grouped[m_name][loc].append({"chassis": chassis, "channels": channels})

        context = {
            "grouped_chassis": grouped,
            "title": "Hardware Layout Overview",
            "opts": self.model._meta,
        }
        return render(request, "admin/micboard/hardware_layout.html", context)

    @admin.display(
        description="Manufacturer",
        ordering="manufacturer__name",
    )
    def manufacturer_display(self, obj):
        """Display manufacturer name."""
        return obj.manufacturer.name if obj.manufacturer else "Unknown"

    @admin.display(description="Hardware Layout")
    def get_hardware_summary(self, obj):
        """Show hardware summary for this chassis."""
        channels = obj.rf_channels.select_related(
            "active_wireless_unit", "active_iem_receiver"
        ).prefetch_related("assignments__user", "assignments__location")

        summary = []
        for channel in channels.order_by("channel_number"):
            unit = channel.active_wireless_unit or channel.active_iem_receiver
            unit_info = "No Unit" if not unit else f"{unit.device_type.upper()}"
            assignments = channel.assignments.filter(is_active=True)
            user_info = assignments.first().user.username if assignments.exists() else "Unassigned"
            summary.append(f"CH{channel.channel_number}: {unit_info} → {user_info}")

        return " | ".join(summary)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["hardware_layout_url"] = "hardware-layout/"
        return super().changelist_view(request, extra_context)

    @admin.display(
        description="Status",
        ordering="status",
    )
    def status_indicator(self, obj):
        """Display colored status indicator."""
        if obj.is_online:
            return format_html(
                '<span style="color: var(--success-fg, green); font-weight: bold;">● Online</span>',
            )
        return format_html(
            '<span style="color: var(--error-fg, red); font-weight: bold;">● Offline</span>',
        )

    @admin.action(description="Mark selected chassis as online")
    def mark_online(self, request, queryset):
        """Mark selected chassis as online."""
        from micboard.services import HardwareService

        updated = 0
        for chassis in queryset:
            HardwareService.sync_hardware_status(obj=chassis, online=True)
            updated += 1
        self.message_user(request, f"{updated} chassis marked as online.")

    @admin.action(description="Mark selected chassis as offline")
    def mark_offline(self, request, queryset):
        """Mark selected chassis as offline."""
        from micboard.services import HardwareService

        updated = 0
        for chassis in queryset:
            HardwareService.sync_hardware_status(obj=chassis, online=False)
            updated += 1
        self.message_user(request, f"{updated} chassis marked as offline.")

    @admin.action(description="Sync selected chassis from API")
    def sync_from_api(self, request, queryset):
        """Sync selected chassis from manufacturer API."""
        from micboard.tasks.sync.polling import poll_manufacturer_devices
        from micboard.utils.dependencies import HAS_DJANGO_Q

        # If all selected chassis belong to the same manufacturer, run
        # centralized discovery sync which will import/update devices.
        manufacturers = queryset.values_list("manufacturer", flat=True).distinct()
        if manufacturers.count() == 1:
            m_id = manufacturers.first()
            if HAS_DJANGO_Q:
                try:
                    from django_q.tasks import async_task

                    # Enqueue background task for polling
                    async_task(poll_manufacturer_devices, m_id)
                    self.message_user(request, "Discovery sync enqueued for background processing")
                    return
                except Exception as e:
                    logger.exception("Error enqueuing discovery sync from admin: %s", e)
                    self.message_user(request, f"Error: {e}", level="error")
                    # fall back to per-chassis sync after logging
            else:
                # Run synchronously
                poll_manufacturer_devices(m_id)
                self.message_user(request, "Discovery sync completed synchronously")
                return

        synced = 0
        for chassis in queryset:
            try:
                plugin_class = chassis.manufacturer.get_plugin_class()
                plugin = plugin_class(chassis.manufacturer)
                device_data = plugin.get_device(chassis.api_device_id)
                if device_data:
                    transformed_data = plugin.transform_device_data(device_data)
                    chassis.name = transformed_data.get("name", chassis.name)
                    chassis.firmware_version = transformed_data.get(
                        "firmware", chassis.firmware_version
                    )
                    # Use HardwareService for status update
                    from micboard.services import HardwareService

                    HardwareService.sync_hardware_status(obj=chassis, online=True)
                    synced += 1
            except Exception as e:
                logger.error("Failed to sync %s: %s", chassis.api_device_id, e)
                self.message_user(
                    request,
                    f"Error syncing {chassis.name}: {e}",
                    level="error",
                )
        if synced > 0:
            self.message_user(request, f"{synced} chassis synced from API.")

    @admin.display(description="Band Plan")
    def band_plan_display(self, obj):
        """Display chassis band plan information."""
        if obj.has_band_plan():
            range_str = f"{obj.band_plan_min_mhz}-{obj.band_plan_max_mhz} MHz"
            if obj.band_plan_name:
                return format_html(
                    '<span style="font-weight: bold;">{}</span><br/>'
                    '<span style="color: gray; font-size: 0.9em;">{}</span>',
                    obj.band_plan_name,
                    range_str,
                )
            return format_html("<span>{}</span>", range_str)
        return format_html('<span style="color: gray;">—</span>')

    @admin.display(description="Band Plan Regulatory Status")
    def band_plan_regulatory_status_display(self, obj):
        """Display band plan regulatory coverage status with color coding."""
        status = obj.get_band_plan_regulatory_status()

        if not status["has_band_plan"]:
            return format_html('<span style="color: gray;">ℹ️ No band plan</span>')

        if status["needs_update"]:
            return format_html(
                '<span style="color: red; font-weight: bold;">⚠️ Missing coverage</span>'
            )

        if status["has_coverage"]:
            return format_html('<span style="color: green;">✅ OK</span>')

        return format_html('<span style="color: gray;">—</span>')
