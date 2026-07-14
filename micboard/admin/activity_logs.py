"""Django admin configuration for logging models.

Split from configuration_and_logging.py — logging-only admin classes.
"""

from __future__ import annotations

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.audit.activity_log import ActivityLog, ServiceSyncLog


@admin.register(ActivityLog)
class ActivityLogAdmin(MicboardModelAdmin):
    """Admin for ActivityLog."""

    list_display = (
        "summary",
        "activity_type_badge",
        "operation_badge",
        "user_name",
        "status_badge",
        "created_at",
    )
    list_filter = ("activity_type", "operation", "status", "created_at")
    search_fields = ("summary", "user__username", "service_code")
    list_select_related = ("user", "content_type")
    readonly_fields = (
        "activity_type",
        "operation",
        "user",
        "service_code",
        "content_type",
        "object_id",
        "summary",
        "details",
        "old_values",
        "new_values",
        "status",
        "error_message",
        "ip_address",
        "user_agent",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"

    fieldsets = (
        (
            "Activity",
            {
                "fields": (
                    "activity_type",
                    "operation",
                    "status",
                    "summary",
                ),
            },
        ),
        (
            "Actor",
            {
                "fields": ("user", "service_code"),
            },
        ),
        (
            "Subject",
            {
                "fields": ("content_type", "object_id"),
            },
        ),
        (
            "Data",
            {
                "fields": ("details", "old_values", "new_values"),
            },
        ),
        (
            "Error",
            {
                "fields": ("error_message",),
                "classes": ("collapse",),
            },
        ),
        (
            "Network",
            {
                "fields": ("ip_address", "user_agent"),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Type")
    def activity_type_badge(self, obj: ActivityLog) -> str:
        """Display activity type as colored badge."""
        colors = {
            "crud": "#0066cc",
            "service": "#ff9900",
            "sync": "#00cc00",
            "config": "#9900cc",
            "discovery": "var(--link-fg, #00cccc)",
            "alert": "var(--error-fg, #cc0000)",
        }
        color = colors.get(obj.activity_type, "var(--body-fg, #666666)")
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_activity_type_display(),
        )

    @admin.display(description="Operation")
    def operation_badge(self, obj: ActivityLog) -> str:
        """Display operation as colored badge."""
        colors = {
            "create": "#00cc00",
            "update": "#ff9900",
            "delete": "#cc0000",
            "read": "#0099cc",
            "start": "#00cc00",
            "stop": "#cc0000",
            "success": "#00cc00",
            "failure": "#cc0000",
            "warning": "var(--warning-fg, #ff9900)",
        }
        color = colors.get(obj.operation, "var(--body-fg, #666666)")
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_operation_display(),
        )

    @admin.display(description="User/Service")
    def user_name(self, obj: ActivityLog) -> str:
        """Display user name."""
        if obj.user:
            url = reverse(
                "admin:auth_user_change",
                args=[obj.user.id],
            )
            return format_html(
                '<a href="{}">{}</a>',
                url,
                obj.user.username,
            )
        if obj.service_code:
            return f"[{obj.service_code}]"
        return "System"

    @admin.display(description="Status")
    def status_badge(self, obj: ActivityLog) -> str:
        """Display status as colored badge."""
        colors = {
            "success": "var(--success-fg, green)",
            "failed": "var(--error-fg, red)",
            "warning": "var(--warning-fg, orange)",
        }
        color = colors.get(obj.status, "var(--body-quiet-color, gray)")
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.status.upper(),
        )


@admin.register(ServiceSyncLog)
class ServiceSyncLogAdmin(MicboardModelAdmin):
    """Admin for ServiceSyncLog."""

    list_display = (
        "service_name",
        "sync_type_badge",
        "status_badge",
        "device_count",
        "online_count",
        "duration",
        "started_at",
    )
    list_filter = ("sync_type", "status", "started_at")
    search_fields = ("service__name", "service__code")
    list_select_related = ("service",)
    readonly_fields = (
        "service",
        "sync_type",
        "started_at",
        "completed_at",
        "device_count",
        "online_count",
        "offline_count",
        "updated_count",
        "status",
        "error_message",
        "details",
        "duration_display",
    )
    date_hierarchy = "started_at"

    fieldsets = (
        (
            "Sync Information",
            {
                "fields": (
                    "service",
                    "sync_type",
                    "status",
                ),
            },
        ),
        (
            "Timeline",
            {
                "fields": ("started_at", "completed_at", "duration_display"),
            },
        ),
        (
            "Results",
            {
                "fields": (
                    "device_count",
                    "online_count",
                    "offline_count",
                    "updated_count",
                ),
            },
        ),
        (
            "Details",
            {
                "fields": ("details",),
            },
        ),
        (
            "Error",
            {
                "fields": ("error_message",),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Service")
    def service_name(self, obj: ServiceSyncLog) -> str:
        """Display service name."""
        return obj.service.name

    @admin.display(description="Type")
    def sync_type_badge(self, obj: ServiceSyncLog) -> str:
        """Display sync type as badge."""
        colors = {
            "refresh": "var(--link-fg, #0099cc)",
            "discovery": "var(--success-fg, #00cc00)",
            "health_check": "var(--warning-fg, #ff9900)",
        }
        color = colors.get(obj.sync_type, "var(--body-quiet-color, gray)")
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.get_sync_type_display(),
        )

    @admin.display(description="Status")
    def status_badge(self, obj: ServiceSyncLog) -> str:
        """Display status as colored badge."""
        colors = {
            "success": "var(--success-fg, green)",
            "partial": "var(--warning-fg, orange)",
            "failed": "var(--error-fg, red)",
        }
        color = colors.get(obj.status, "var(--body-quiet-color, gray)")
        return format_html(
            '<span style="color: {};">{}</span>',
            color,
            obj.status.upper(),
        )

    @admin.display(description="Duration")
    def duration(self, obj: ServiceSyncLog) -> str:
        """Display sync duration."""
        seconds = obj.duration_seconds()
        if seconds < 60:
            return f"{seconds}s"
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}m {seconds}s"

    @admin.display(description="Duration")
    def duration_display(self, obj: ServiceSyncLog) -> str:
        """Display duration for detail view."""
        return f"{obj.duration_seconds()} seconds"
