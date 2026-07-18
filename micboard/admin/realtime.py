"""Admin interface for real-time connection monitoring."""

from typing import Any

from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.realtime.connection import RealTimeConnection
from micboard.services.realtime.connection_service import (
    connection_duration,
    time_since_last_message,
)


@admin.register(RealTimeConnection)
class RealTimeConnectionAdmin(MicboardModelAdmin):
    """Admin interface for RealTimeConnection model."""

    list_display = [
        "chassis",
        "connection_type",
        "status_colored",
        "connected_at",
        "last_message_at",
        "connection_duration",
        "error_count",
    ]

    list_filter = [
        "connection_type",
        "status",
        "connected_at",
        "last_message_at",
        "error_count",
    ]

    search_fields = [
        "chassis__name",
        "chassis__ip",
        "chassis__manufacturer__name",
        "error_message",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
        "connected_at",
        "last_message_at",
        "disconnected_at",
        "last_error_at",
        "connection_duration",
        "time_since_last_message",
    ]

    fieldsets = (
        ("Device Information", {"fields": ("chassis", "connection_type")}),
        (
            "Connection Status",
            {"fields": ("status", "connected_at", "last_message_at", "disconnected_at")},
        ),
        ("Error Tracking", {"fields": ("error_message", "error_count", "last_error_at")}),
        ("Configuration", {"fields": ("reconnect_attempts", "max_reconnect_attempts")}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    actions = [
        "mark_connected",
        "mark_disconnected",
        "reset_error_count",
        "stop_connections",
    ]

    @admin.display(
        description="Status",
        ordering="status",
    )
    def status_colored(self, obj: Any) -> Any:
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
    def connection_duration(self, obj: Any) -> Any:
        """Display connection duration."""
        duration = connection_duration(obj)
        if duration:
            total_seconds = int(duration.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return "-"

    @admin.display(description="Since Last Message")
    def time_since_last_message(self, obj: Any) -> Any:
        """Display time since last message."""
        elapsed = time_since_last_message(obj)
        if elapsed:
            total_seconds = int(elapsed.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return "-"

    @admin.action(permissions=["change"], description="Mark as connected")
    def mark_connected(self, request: Any, queryset: Any) -> None:
        """Mark selected connections as connected."""
        updated = queryset.update(
            status="connected",
            connected_at=timezone.now(),
            last_message_at=timezone.now(),
            error_count=0,
            error_message="",
        )
        self.message_user(request, f"Marked {updated} connection(s) as connected.")

    @admin.action(permissions=["change"], description="Mark as disconnected")
    def mark_disconnected(self, request: Any, queryset: Any) -> None:
        """Mark selected connections as disconnected."""
        updated = queryset.update(status="disconnected", disconnected_at=timezone.now())
        self.message_user(request, f"Marked {updated} connection(s) as disconnected.")

    @admin.action(permissions=["change"], description="Reset error count")
    def reset_error_count(self, request: Any, queryset: Any) -> None:
        """Reset error count for selected connections."""
        updated = queryset.update(error_count=0, error_message="")
        self.message_user(request, f"Reset error count for {updated} connection(s).")

    @admin.action(permissions=["change"], description="Stop connections")
    def stop_connections(self, request: Any, queryset: Any) -> None:
        """Stop selected connections."""
        updated = queryset.update(status="stopped", disconnected_at=timezone.now())
        self.message_user(request, f"Stopped {updated} connection(s).")

    def get_queryset(self, request: Any) -> Any:
        """Optimize queryset with select_related."""
        return super().get_queryset(request).select_related("chassis", "chassis__manufacturer")
