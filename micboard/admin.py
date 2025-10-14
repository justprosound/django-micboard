from django.contrib import admin

# Updated imports
from .models import (
    Alert,
    Channel,
    DeviceAssignment,
    DiscoveredDevice,
    Group,
    Location,
    MicboardConfig,
    MonitoringGroup,  # Assuming MonitoringGroup and Location are defined elsewhere or will be created
    Receiver,
    Transmitter,
    UserAlertPreference,
)


# Inline for Channels within Receiver admin
class ChannelInline(admin.StackedInline):
    model = Channel
    extra = 1  # Number of empty forms to display


# Inline for Transmitters within Channel admin
class TransmitterInline(admin.StackedInline):
    model = Transmitter
    extra = 1


@admin.register(Receiver)
class ReceiverAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "device_type",
        "ip",
        "api_device_id",
        "is_active",
        "last_seen",
    )
    list_filter = ("device_type", "is_active")
    search_fields = ("name", "ip", "api_device_id")
    inlines = [ChannelInline]  # Add ChannelInline here


@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "receiver", "channel_number")
    list_filter = ("receiver__device_type", "receiver__is_active")
    search_fields = ("receiver__name", "channel_number")
    inlines = [TransmitterInline]  # Add TransmitterInline here


@admin.register(Transmitter)
class TransmitterAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "channel",
        "slot",
        "battery",
        "audio_level",
        "rf_level",
        "status",
    )
    list_filter = ("channel__receiver__device_type", "status")
    search_fields = ("channel__receiver__name", "slot", "name")


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
    list_display = ("channel", "user", "alert_type", "status", "created_at")  # Updated from device
    list_filter = ("alert_type", "status", "user")
    search_fields = (
        "channel__receiver__name",
        "channel__channel_number",
        "user__username",
        "message",
    )  # Updated


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
