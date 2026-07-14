"""Admin configuration for wireless chassis and units.

This module provides Django admin interfaces for managing wireless audio hardware.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import render
from django.urls import path
from django.utils.html import format_html

from micboard.admin.forms import WirelessChassisAdminForm
from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.integrations import Accessory
from micboard.models.rf_coordination.rf_channel import RFChannel
from micboard.services.hardware.wireless_unit_service import get_battery_percentage

logger = logging.getLogger(__name__)
MAX_SYNCHRONOUS_REFRESH = 25


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

    @admin.display(description="Battery Percentage", ordering="battery")
    def battery_percentage(self, obj: WirelessUnit) -> int | None:
        """Expose normalized battery percentage as an inline readonly field."""
        return get_battery_percentage(obj)


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

    def delete_queryset(self, request, queryset) -> None:
        """Register one post-commit discovery cleanup for bulk deletion."""
        from micboard.model_lifecycle import suppress_chassis_delete_hooks
        from micboard.services.core.hardware_post_save_hooks import HardwarePostSaveHooks

        using = queryset.db
        with transaction.atomic(using=using):
            chassis_ids = list(queryset.values_list("pk", flat=True))
            chassis_list = list(
                WirelessChassis._default_manager.using(using)
                .select_for_update()
                .filter(pk__in=chassis_ids)
                .order_by("pk")
            )
            HardwarePostSaveHooks.handle_chassis_bulk_delete(
                chassis_list=chassis_list,
                using=using,
            )
            deletion_queryset = WirelessChassis._default_manager.using(using).filter(
                pk__in=chassis_ids
            )
            with suppress_chassis_delete_hooks():
                super().delete_queryset(request, deletion_queryset)

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
        if not self.has_view_permission(request):
            raise PermissionDenied

        chassis_qs = (
            self.get_queryset(request)
            .filter(status__in=["online", "degraded", "provisioning"])
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
                '<span style="color: var(--success-fg, green); font-weight: bold;">{}</span>',
                "● Online",
            )
        return format_html(
            '<span style="color: var(--error-fg, red); font-weight: bold;">{}</span>',
            "● Offline",
        )

    @admin.action(permissions=["change"], description="Mark selected chassis as online")
    def mark_online(self, request, queryset):
        """Mark selected chassis as online."""
        from micboard.services.core.hardware import HardwareService

        updated = 0
        for chassis in queryset:
            HardwareService.sync_hardware_status(obj=chassis, online=True)
            updated += 1
        self.message_user(request, f"{updated} chassis marked as online.")

    @admin.action(permissions=["change"], description="Mark selected chassis as offline")
    def mark_offline(self, request, queryset):
        """Mark selected chassis as offline."""
        from micboard.services.core.hardware import HardwareService

        updated = 0
        for chassis in queryset:
            HardwareService.sync_hardware_status(obj=chassis, online=False)
            updated += 1
        self.message_user(request, f"{updated} chassis marked as offline.")

    @admin.action(permissions=["change"], description="Sync selected chassis from API")
    def sync_from_api(self, request, queryset):
        """Sync exactly the tenant-scoped chassis selected by the operator."""
        from micboard.services.hardware.chassis_refresh_service import ChassisRefreshService
        from micboard.tasks.sync.polling import refresh_selected_chassis
        from micboard.utils.dependencies import enqueue_huey_task, huey_is_configured

        using = queryset.db
        chassis_ids = list(queryset.order_by("pk").values_list("pk", flat=True))
        if not chassis_ids:
            self.message_user(request, "No chassis selected.", level=messages.WARNING)
            return
        if huey_is_configured():
            enqueue_huey_task(refresh_selected_chassis, chassis_ids, using=using)
            self.message_user(
                request,
                f"Queued {len(chassis_ids)} chassis for API refresh.",
                level=messages.SUCCESS,
            )
            return
        if len(chassis_ids) > MAX_SYNCHRONOUS_REFRESH:
            self.message_user(
                request,
                "Native Huey must be configured to refresh more than "
                f"{MAX_SYNCHRONOUS_REFRESH} chassis at once.",
                level=messages.ERROR,
            )
            return

        result = ChassisRefreshService.refresh_ids(chassis_ids=chassis_ids, using=using)
        if result.synced_count:
            self.message_user(request, f"{result.synced_count} chassis synced from API.")
        if result.failed_count:
            self.message_user(
                request,
                f"{result.failed_count} chassis could not be synced. Check logs for details.",
                level="warning",
            )

    @admin.display(description="Band Plan")
    def band_plan_display(self, obj):
        """Display chassis band plan information."""
        from micboard.services.hardware.wireless_chassis_service import get_band_plan_status

        if get_band_plan_status(obj):
            range_str = f"{obj.band_plan_min_mhz}-{obj.band_plan_max_mhz} MHz"
            if obj.band_plan_name:
                return format_html(
                    '<span style="font-weight: bold;">{}</span><br/>'
                    '<span style="color: gray; font-size: 0.9em;">{}</span>',
                    obj.band_plan_name,
                    range_str,
                )
            return format_html("<span>{}</span>", range_str)
        return format_html('<span style="color: gray;">{}</span>', "—")

    @admin.display(description="Band Plan Regulatory Status")
    def band_plan_regulatory_status_display(self, obj):
        """Display band plan regulatory coverage status with color coding."""
        from micboard.services.hardware.chassis_regulatory_service import (
            get_band_plan_regulatory_status,
        )

        status = get_band_plan_regulatory_status(obj)

        if not status["has_band_plan"]:
            return format_html('<span style="color: gray;">{}</span>', "No band plan")

        if status["needs_update"]:
            return format_html(
                '<span style="color: red; font-weight: bold;">{}</span>',
                "⚠️ Missing coverage",
            )

        if status["has_coverage"]:
            return format_html('<span style="color: green;">{}</span>', "✅ OK")

        return format_html('<span style="color: gray;">{}</span>', "—")
