from django.contrib import admin

from micboard.admin.mixins import MicboardModelAdmin
from micboard.models import Alert, Performer, PerformerAssignment, UserAlertPreference


@admin.register(Performer)
class PerformerAdmin(MicboardModelAdmin):
    list_display = ("name", "title", "email", "phone", "is_active", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "title", "email", "phone", "notes")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Basic Information", {"fields": ("name", "title", "photo", "is_active")}),
        ("Contact Information", {"fields": ("email", "phone")}),
        ("Additional Details", {"fields": ("notes",)}),
        ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )


@admin.register(PerformerAssignment)
class PerformerAssignmentAdmin(MicboardModelAdmin):
    list_display = (
        "performer",
        "wireless_unit",
        "monitoring_group",
        "priority",
        "is_active",
        "assigned_at",
    )
    list_filter = (
        "priority",
        "is_active",
        "alert_on_battery_low",
        "alert_on_signal_loss",
        "alert_on_audio_low",
        "alert_on_hardware_offline",
    )
    search_fields = ("performer__name", "wireless_unit__name", "monitoring_group__name", "notes")
    list_select_related = ("performer", "wireless_unit", "monitoring_group", "assigned_by")
    readonly_fields = ("assigned_at", "updated_at", "assigned_by")
    raw_id_fields = ("performer", "wireless_unit", "monitoring_group", "assigned_by")

    fieldsets = (
        (
            "Assignment",
            {"fields": ("performer", "wireless_unit", "monitoring_group", "priority", "is_active")},
        ),
        (
            "Alert Settings",
            {
                "fields": (
                    "alert_on_battery_low",
                    "alert_on_signal_loss",
                    "alert_on_audio_low",
                    "alert_on_hardware_offline",
                )
            },
        ),
        ("Notes", {"fields": ("notes",)}),
        (
            "Audit Trail",
            {"fields": ("assigned_by", "assigned_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(UserAlertPreference)
class UserAlertPreferenceAdmin(MicboardModelAdmin):
    list_display = ("user", "notification_method", "battery_low_threshold", "quiet_hours_enabled")
    list_filter = ("notification_method", "quiet_hours_enabled")
    search_fields = ("user__username",)
    list_select_related = ("user",)


@admin.register(Alert)
class AlertAdmin(MicboardModelAdmin):
    list_display = (
        "channel",
        "user",
        "alert_type",
        "status",
        "severity",
        "is_overdue",
        "created_at",
    )
    list_filter = ("alert_type", "status", "created_at", "channel__chassis__manufacturer")
    search_fields = (
        "channel__chassis__name",
        "channel__channel_number",
        "user__username",
        "message",
    )
    list_select_related = ("channel", "channel__chassis", "user", "assignment")
    readonly_fields = ("created_at", "acknowledged_at", "resolved_at", "is_overdue")
    date_hierarchy = "created_at"
