from django.contrib import admin

from micboard.models import Alert, DeviceAssignment, UserAlertPreference


@admin.register(DeviceAssignment)
class DeviceAssignmentAdmin(admin.ModelAdmin):
    list_display = ("user", "get_role", "channel", "priority", "is_active")
    list_filter = ("priority", "is_active", "user__profile__user_type")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "channel__chassis__name",
    )

    @admin.display(description="Performer Title")
    def get_role(self, obj):
        return obj.user.profile.title if hasattr(obj.user, "profile") else "-"

    raw_id_fields = ("user", "channel")


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
    readonly_fields = ("created_at", "acknowledged_at", "resolved_at", "is_overdue")
    date_hierarchy = "created_at"
