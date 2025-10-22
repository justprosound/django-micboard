"""
Admin configuration for receiver models (Receiver, Channel, Transmitter).

This module provides Django admin interfaces for managing wireless audio receivers.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from django.contrib import admin
from django.db.models import Count, Prefetch, Q
from django.shortcuts import render
from django.urls import path
from django.utils.html import format_html

from micboard.models import (
    Channel,
    DeviceAssignment,
    Receiver,
    Transmitter,
)

logger = logging.getLogger(__name__)


class TransmitterInline(admin.StackedInline):
    """Inline admin for Transmitter model."""

    model = Transmitter
    extra = 0
    readonly_fields = ("battery_percentage", "updated_at", "slot", "name", "status")
    fields = (
        "slot",
        "name",
        "battery_percentage",
        "audio_level",
        "rf_level",
        "status",
        "updated_at",
    )
    can_delete = False


class ChannelInline(admin.StackedInline):
    """Inline admin for Channel model."""

    model = Channel
    extra = 0  # Don't show empty forms
    readonly_fields = ("channel_number", "get_transmitter_info", "get_assignment_info")
    fields = ("channel_number", "get_transmitter_info", "get_assignment_info")
    can_delete = False
    inlines: ClassVar[list] = [TransmitterInline]

    def get_transmitter_info(self, obj):
        """Show transmitter information for this channel."""
        if hasattr(obj, "transmitter"):
            tx = obj.transmitter
            battery_pct = tx.battery_percentage or "?"
            battery_color = (
                "green" if tx.battery_percentage and tx.battery_percentage > 25 else "red"
            )
            return format_html(
                "<div><strong>Slot {}:</strong> {}<br>"
                "<span style='color: {}'>Battery: {}%</span> | "
                "Audio: {} dB | RF: {} dBm<br>"
                "Status: {} | Updated: {}</div>",
                tx.slot,
                tx.name or f"Transmitter {tx.slot}",
                battery_color,
                battery_pct,
                tx.audio_level,
                tx.rf_level,
                tx.status or "Unknown",
                tx.updated_at.strftime("%H:%M:%S") if tx.updated_at else "Never",
            )
        return "<em>No transmitter assigned</em>"

    get_transmitter_info.short_description = "Transmitter"  # type: ignore

    def get_assignment_info(self, obj):
        """Show assignment information for this channel."""
        assignments = obj.assignments.filter(is_active=True)
        if assignments.exists():
            assignment = assignments.first()
            return format_html(
                "<div><strong>User:</strong> {}<br>"
                "<strong>Location:</strong> {}<br>"
                "<strong>Priority:</strong> {}<br>"
                "<strong>Group:</strong> {}</div>",
                assignment.user.username,
                assignment.location.full_address if assignment.location else "Not set",
                assignment.priority.title(),
                assignment.monitoring_group.name if assignment.monitoring_group else "None",
            )
        return "<em>No active assignment</em>"

    get_assignment_info.short_description = "Assignment"  # type: ignore


@admin.register(Receiver)
class ReceiverAdmin(admin.ModelAdmin):
    """Admin configuration for Receiver model."""

    list_display = (
        "name",
        "device_type",
        "manufacturer_display",
        "ip",
        "api_device_id",
        "status_indicator",
        "channel_count",
        "active_transmitters",
        "last_seen",
    )
    list_filter = ("device_type", "is_active", "manufacturer")
    search_fields = ("name", "ip", "api_device_id")
    inlines: ClassVar[list] = [ChannelInline]
    readonly_fields = ("last_seen", "get_hardware_summary")
    date_hierarchy = "last_seen"
    actions: ClassVar[list[str]] = ["mark_online", "mark_offline", "sync_from_api"]
    change_form_template = "admin/micboard/receiver_change_form.html"
    change_list_template = "admin/micboard/receiver_changelist.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "hardware-layout/",
                self.admin_site.admin_view(self.hardware_layout_view),
                name="micboard_receiver_hardware_layout",
            ),
        ]
        return custom_urls + urls

    def hardware_layout_view(self, request):
        """Custom view showing hardware layout for all receivers.

        Build a compact structure grouped by manufacturer and receiver ip, then
        for each receiver list channels with their current frequency (if any).
        """
        receivers_qs = (
            Receiver.objects.filter(is_active=True)
            .select_related("manufacturer")
            .prefetch_related(
                "channels__transmitter",
                Prefetch(
                    "channels__assignments",
                    queryset=DeviceAssignment.objects.filter(is_active=True).select_related(
                        "user", "location"
                    ),
                    to_attr="active_assignments",
                ),
            )
            .annotate(
                channel_count=Count("channels"),
                transmitter_count=Count("channels", filter=Q(channels__transmitter__isnull=False)),
            )
            .order_by("manufacturer__name", "ip")
        )

        # Build grouped structure for template to avoid complex template logic
        grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for r in receivers_qs:
            m_name = r.manufacturer.name if r.manufacturer else "Unknown"
            grouped.setdefault(m_name, {})
            # Use ip as receiver location identifier
            loc = r.ip or "Unknown IP"
            grouped[m_name].setdefault(loc, [])

            channels = []
            for ch in r.channels.all().order_by("channel_number"):
                freq = None
                if hasattr(ch, "transmitter") and getattr(ch.transmitter, "frequency", None):
                    freq = ch.transmitter.frequency
                channels.append({"channel_number": ch.channel_number, "frequency": freq})

            grouped[m_name][loc].append({"receiver": r, "channels": channels})

        context = {
            "grouped_receivers": grouped,
            "title": "Hardware Layout Overview",
            "opts": self.model._meta,
        }
        return render(request, "admin/micboard/hardware_layout.html", context)

    def manufacturer_display(self, obj):
        """Display manufacturer name."""
        return obj.manufacturer.name if obj.manufacturer else "Unknown"

    manufacturer_display.short_description = "Manufacturer"  # type: ignore
    manufacturer_display.admin_order_field = "manufacturer__name"  # type: ignore

    def channel_count(self, obj):
        """Show number of channels."""
        return obj.channels.count()

    channel_count.short_description = "Channels"  # type: ignore

    def active_transmitters(self, obj):
        """Show number of active transmitters."""
        return obj.channels.filter(transmitter__isnull=False).count()

    active_transmitters.short_description = "Active TX"  # type: ignore

    def get_hardware_summary(self, obj):
        """Show hardware summary for this receiver."""
        channels = obj.channels.select_related("transmitter").prefetch_related(
            "assignments__user", "assignments__location"
        )

        summary = []
        for channel in channels.order_by("channel_number"):
            tx_info = (
                "No TX"
                if not hasattr(channel, "transmitter")
                else f"TX Slot {channel.transmitter.slot}"
            )
            assignments = channel.assignments.filter(is_active=True)
            user_info = assignments.first().user.username if assignments.exists() else "Unassigned"
            summary.append(f"CH{channel.channel_number}: {tx_info} → {user_info}")

        return format_html("<br>".join(summary))

    get_hardware_summary.short_description = "Hardware Layout"  # type: ignore

    fieldsets = (
        (
            "Device Information",
            {
                "fields": (
                    "manufacturer",
                    "name",
                    "device_type",
                    "ip",
                    "api_device_id",
                    "firmware_version",
                )
            },
        ),
        ("Status", {"fields": ("is_active", "last_seen")}),
        (
            "Hardware Layout",
            {
                "fields": ("get_hardware_summary",),
                "classes": ("collapse",),
            },
        ),
    )

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["hardware_layout_url"] = "hardware-layout/"
        return super().changelist_view(request, extra_context)

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
        from django_q.tasks import async_task

        from micboard.tasks.polling_tasks import poll_manufacturer_devices

        # If all selected receivers belong to the same manufacturer, run
        # centralized discovery sync which will import/update receivers.
        manufacturers = queryset.values_list("manufacturer", flat=True).distinct()
        if manufacturers.count() == 1:
            m_id = manufacturers.first()
            try:
                # Enqueue background task for polling
                async_task(poll_manufacturer_devices, m_id)
                self.message_user(request, "Discovery sync enqueued for background processing")
                return
            except Exception as e:
                logger.exception("Error enqueuing discovery sync from admin: %s", e)
                self.message_user(request, f"Error: {e}", level="error")
                # fall back to per-receiver sync after logging
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
