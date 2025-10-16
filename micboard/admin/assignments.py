"""
Admin configuration for assignment models (DeviceAssignment, Alert, UserAlertPreference).

This module provides Django admin interfaces for managing device-to-user assignments and alerts.
"""

from __future__ import annotations

from typing import ClassVar

from django.contrib import admin
from django.utils.html import format_html

from micboard.models import Alert, DeviceAssignment, UserAlertPreference


@admin.register(DeviceAssignment)
class DeviceAssignmentAdmin(admin.ModelAdmin):
    """Admin configuration for DeviceAssignment model."""

    list_display = (
        "user",
        "channel",
        "location",
        "monitoring_group",
        "priority",
        "is_active",
    )
    list_filter = (
        "priority",
        "is_active",
        "user",
        "location",
        "monitoring_group",
        "channel__receiver__manufacturer",
    )
    search_fields = (
        "user__username",
        "channel__receiver__name",
        "channel__channel_number",
    )


@admin.register(UserAlertPreference)
class UserAlertPreferenceAdmin(admin.ModelAdmin):
    """Admin configuration for UserAlertPreference model."""

    list_display = ("user", "notification_method", "battery_low_threshold", "quiet_hours_enabled")
    list_filter = ("notification_method", "quiet_hours_enabled")
    search_fields = ("user__username",)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    """Admin configuration for Alert model."""

    list_display = (
        "channel",
        "user",
        "alert_type",
        "status_indicator",
        "severity",
        "is_overdue",
        "created_at",
    )
    list_filter = ("alert_type", "status", "created_at", "channel__receiver__manufacturer")
    search_fields = (
        "channel__receiver__name",
        "channel__channel_number",
        "user__username",
        "message",
    )
    readonly_fields = ("created_at", "acknowledged_at", "resolved_at", "is_overdue")
    date_hierarchy = "created_at"
    actions: ClassVar[list[str]] = ["acknowledge_alerts", "resolve_alerts"]

    def status_indicator(self, obj):
        """Display colored status indicator."""
        status_colors = {
            "pending": "orange",
            "acknowledged": "blue",
            "resolved": "green",
        }
        color = status_colors.get(obj.status, "gray")
        return format_html(
            '<span style="color: {}; font-weight: bold;">● {}</span>',
            color,
            obj.status.title(),
        )

    status_indicator.short_description = "Status"  # type: ignore
    status_indicator.admin_order_field = "status"  # type: ignore

    @admin.action(description="Acknowledge selected alerts")
    def acknowledge_alerts(self, request, queryset):
        """Acknowledge selected alerts."""
        updated = 0
        for alert in queryset.filter(status="pending"):
            alert.acknowledge(request.user)
            updated += 1
        self.message_user(request, f"{updated} alert(s) acknowledged.")

    @admin.action(description="Resolve selected alerts")
    def resolve_alerts(self, request, queryset):
        """Resolve selected alerts."""
        updated = 0
        for alert in queryset.exclude(status="resolved"):
            alert.resolve()
            updated += 1
        self.message_user(request, f"{updated} alert(s) resolved.")
