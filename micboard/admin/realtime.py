"""Admin interface for real-time connection monitoring."""

from typing import ClassVar

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from micboard.models import RealTimeConnection


@admin.register(RealTimeConnection)
class RealTimeConnectionAdmin(admin.ModelAdmin):
    """Admin interface for RealTimeConnection model."""

    list_display: ClassVar[list[str]] = [
        "receiver",
        "connection_type",
        "status_colored",
        "connected_at",
        "last_message_at",
        "connection_duration",
        "error_count",
    ]

    list_filter: ClassVar[list[str]] = [
        "connection_type",
        "status",
        "connected_at",
        "last_message_at",
        "error_count",
    ]

    search_fields: ClassVar[list[str]] = [
        "receiver__name",
        "receiver__ip",
        "receiver__manufacturer__name",
        "error_message",
    ]

    readonly_fields: ClassVar[list[str]] = [
        "created_at",
        "updated_at",
        "connected_at",
        "last_message_at",
        "disconnected_at",
        "last_error_at",
        "connection_duration",
        "time_since_last_message",
    ]

    fieldsets: ClassVar[tuple] = (
        ("Device Information", {"fields": ("receiver", "connection_type")}),
        (
            "Connection Status",
            {"fields": ("status", "connected_at", "last_message_at", "disconnected_at")},
        ),
        ("Error Tracking", {"fields": ("error_message", "error_count", "last_error_at")}),
        ("Configuration", {"fields": ("reconnect_attempts", "max_reconnect_attempts")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    actions: ClassVar[list[str]] = [
        "mark_connected",
        "mark_disconnected",
        "reset_error_count",
        "stop_connections",
    ]

    @admin.display(
        description="Status",
        ordering="status",
    )
    def status_colored(self, obj):
        """Display status with color coding."""
        colors = {
            "connected": "var(--success-fg, green)",
            "connecting": "var(--warning-fg, orange)",
            "disconnected": "var(--body-quiet-color, gray)",
            "error": "var(--error-fg, red)",
            "stopped": "var(--link-fg, blue)",
        }
        color = colors.get(obj.status, "var(--body-fg, black)")
        return format_html('<span style="color: {};">{}</span>', color, obj.get_status_display())

    @admin.display(description="Duration")
    def connection_duration(self, obj):
        """Display connection duration."""
        if obj.connection_duration:
            total_seconds = int(obj.connection_duration.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return "-"

    @admin.display(description="Since Last Message")
    def time_since_last_message(self, obj):
        """Display time since last message."""
        if obj.time_since_last_message:
            total_seconds = int(obj.time_since_last_message.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return "-"

    @admin.action(description="Mark as connected")
    def mark_connected(self, request, queryset):
        """Mark selected connections as connected."""
        updated = queryset.update(
            status="connected",
            connected_at=timezone.now(),
            last_message_at=timezone.now(),
            error_count=0,
            error_message="",
        )
        self.message_user(request, f"Marked {updated} connection(s) as connected.")

    @admin.action(description="Mark as disconnected")
    def mark_disconnected(self, request, queryset):
        """Mark selected connections as disconnected."""
        updated = queryset.update(status="disconnected", disconnected_at=timezone.now())
        self.message_user(request, f"Marked {updated} connection(s) as disconnected.")

    @admin.action(description="Reset error count")
    def reset_error_count(self, request, queryset):
        """Reset error count for selected connections."""
        updated = queryset.update(error_count=0, error_message="")
        self.message_user(request, f"Reset error count for {updated} connection(s).")

    @admin.action(description="Stop connections")
    def stop_connections(self, request, queryset):
        """Stop selected connections."""
        updated = queryset.update(status="stopped", disconnected_at=timezone.now())
        self.message_user(request, f"Stopped {updated} connection(s).")

    def get_queryset(self, request):
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related("receiver", "receiver__manufacturer")
