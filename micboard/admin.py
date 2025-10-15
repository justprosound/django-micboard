"""
Django admin configuration for the micboard app.
"""
import logging

from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from micboard.shure_api_client import ShureSystemAPIClient

# Updated imports
from micboard.models import (
    Alert,
    Channel,
    DeviceAssignment,
    DiscoveredDevice,
    Group,
    Location,
    MicboardConfig,
    MonitoringGroup,
    Receiver,
    Transmitter,
    UserAlertPreference,
)

logger = logging.getLogger(__name__)


class ChannelInline(admin.StackedInline):
    model = Channel
    extra = 1  # Number of empty forms to display
    readonly_fields = ("get_transmitter_status",)

    def get_transmitter_status(self, obj):
        """Show transmitter status in inline"""
        if hasattr(obj, "transmitter"):
            tx = obj.transmitter
            return format_html(
                '<strong>Slot {}:</strong> Battery {}% | Audio {} dB | RF {} dBm',
                tx.slot,
                tx.battery_percentage or "?",
                tx.audio_level,
                tx.rf_level,
            )
        return "No transmitter assigned"

    get_transmitter_status.short_description = "Transmitter Status"


class TransmitterInline(admin.StackedInline):
    model = Transmitter
    extra = 1
    readonly_fields = ("battery_percentage", "updated_at")


@admin.register(Receiver)
class ReceiverAdmin(admin.ModelAdmin):
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
    inlines = [ChannelInline]  # Add ChannelInline here
    readonly_fields = ("last_seen",)
    date_hierarchy = "last_seen"
    actions = ["mark_online", "mark_offline", "sync_from_api"]

    def status_indicator(self, obj):
        """Display colored status indicator"""
        if obj.is_active:
            return format_html(
                '<span style="color: green; font-weight: bold;">● Online</span>',
            )
        return format_html(
            '<span style="color: red; font-weight: bold;">● Offline</span>',
        )

    status_indicator.short_description = "Status"
    status_indicator.admin_order_field = "is_active"

    @admin.action(description="Mark selected receivers as online")
    def mark_online(self, request, queryset):
        """Mark selected receivers as online"""
        updated = 0
        for receiver in queryset:
            receiver.mark_online()
            updated += 1
        self.message_user(request, f"{updated} receiver(s) marked as online.")

    @admin.action(description="Mark selected receivers as offline")
    def mark_offline(self, request, queryset):
        """Mark selected receivers as offline"""
        updated = 0
        for receiver in queryset:
            receiver.mark_offline()
            updated += 1
        self.message_user(request, f"{updated} receiver(s) marked as offline.")

    @admin.action(description="Sync selected receivers from Shure API")
    def sync_from_api(self, request, queryset):
        """Sync selected receivers from Shure System API"""
        try:
            client = ShureSystemAPIClient()
            synced = 0
            for receiver in queryset:
                try:
                    device_data = client.get_device_by_id(receiver.api_device_id)
                    if device_data:
                        # Update receiver fields
                        receiver.name = device_data.get("name", receiver.name)
                        receiver.firmware_version = device_data.get(
                            "firmware", receiver.firmware_version
                        )
                        receiver.mark_online()
                        synced += 1
                except Exception as e:
                    logger.error(f"Failed to sync {receiver.api_device_id}: {e}")
            self.message_user(request, f"{synced} receiver(s) synced from API.")
        except Exception as e:
            self.message_user(request, f"Error syncing: {e}", level="error")


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "receiver", "channel_number", "has_transmitter")
    list_filter = ("receiver__device_type", "receiver__is_active")
    search_fields = ("receiver__name", "channel_number")
    inlines = [TransmitterInline]  # Add TransmitterInline here

    def has_transmitter(self, obj):
        """Show if channel has transmitter"""
        if hasattr(obj, "transmitter"):
            return format_html(
                '<span style="color: green;">✓ Yes (Slot {})</span>',
                obj.transmitter.slot,
            )
        return format_html('<span style="color: gray;">✗ No</span>')

    has_transmitter.short_description = "Has Transmitter"


@admin.register(Transmitter)
class TransmitterAdmin(admin.ModelAdmin):
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
        """Display colored battery indicator"""
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

    battery_indicator.short_description = "Battery"
    battery_indicator.admin_order_field = "battery"


@admin.register(DeviceAssignment)
class DeviceAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "channel",  # Updated from device
        "location",
        "monitoring_group",
        "priority",
        "is_active",
    )
    list_filter = ("priority", "is_active", "user", "location", "monitoring_group")
    search_fields = (
        "user__username",
        "channel__receiver__name",
        "channel__channel_number",
    )  # Updated


@admin.register(UserAlertPreference)
class UserAlertPreferenceAdmin(admin.ModelAdmin):
    list_display = ("user", "notification_method", "battery_low_threshold", "quiet_hours_enabled")
    list_filter = ("notification_method", "quiet_hours_enabled")
    search_fields = ("user__username",)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = (
        "channel",
        "user",
        "alert_type",
        "status_indicator",
        "severity",
        "is_overdue",
        "created_at",
    )
    list_filter = ("alert_type", "status", "severity", "created_at")
    search_fields = (
        "channel__receiver__name",
        "channel__channel_number",
        "user__username",
        "message",
    )  # Updated
    readonly_fields = ("created_at", "acknowledged_at", "resolved_at", "is_overdue")
    date_hierarchy = "created_at"
    actions = ["acknowledge_alerts", "resolve_alerts"]

    def status_indicator(self, obj):
        """Display colored status indicator"""
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

    status_indicator.short_description = "Status"
    status_indicator.admin_order_field = "status"

    @admin.action(description="Acknowledge selected alerts")
    def acknowledge_alerts(self, request, queryset):
        """Acknowledge selected alerts"""
        updated = 0
        for alert in queryset.filter(status="pending"):
            alert.acknowledge(request.user)
            updated += 1
        self.message_user(request, f"{updated} alert(s) acknowledged.")

    @admin.action(description="Resolve selected alerts")
    def resolve_alerts(self, request, queryset):
        """Resolve selected alerts"""
        updated = 0
        for alert in queryset.exclude(status="resolved"):
            alert.resolve()
            updated += 1
        self.message_user(request, f"{updated} alert(s) resolved.")


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("group_number", "title", "hide_charts")
    search_fields = ("title",)


@admin.register(MicboardConfig)
class MicboardConfigAdmin(admin.ModelAdmin):
    list_display = ("key", "value")
    search_fields = ("key",)


@admin.register(DiscoveredDevice)
class DiscoveredDeviceAdmin(admin.ModelAdmin):
    list_display = ("ip", "device_type", "channels", "discovered_at")
    list_filter = ("device_type",)
    search_fields = ("ip", "device_type")


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "building", "room")
    list_filter = ("building", "room")
    search_fields = ("name", "building", "room")


@admin.register(MonitoringGroup)
class MonitoringGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "location", "is_active")
    list_filter = ("is_active", "location")
    search_fields = ("name", "description")
    filter_horizontal = (
        "users",
        "channels",
    )  # Use filter_horizontal for better UX with many-to-many
