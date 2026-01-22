"""
Django admin configuration for configuration and logging models.
"""

from __future__ import annotations

from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from micboard.models import (
    ActivityLog,
    ConfigurationAuditLog,
    ManufacturerConfiguration,
    ServiceSyncLog,
)


@admin.register(ManufacturerConfiguration)
class ManufacturerConfigurationAdmin(admin.ModelAdmin):
    """Admin for ManufacturerConfiguration."""

    list_display = (
        "name",
        "code",
        "status_badge",
        "validation_badge",
        "is_active",
        "last_validated",
        "updated_by_name",
    )
    list_filter = ("is_active", "is_valid", "created_at")
    search_fields = ("code", "name")
    readonly_fields = (
        "created_at",
        "updated_at",
        "validation_errors",
        "last_validated",
        "is_valid",
        "validation_result",
    )

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": ("code", "name", "is_active"),
            },
        ),
        (
            "Configuration",
            {
                "fields": ("config",),
            },
        ),
        (
            "Validation",
            {
                "fields": (
                    "is_valid",
                    "validation_result",
                    "validation_errors",
                    "last_validated",
                ),
            },
        ),
        (
            "Audit",
            {
                "fields": ("created_at", "updated_at", "updated_by"),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["validate_config", "apply_config", "enable_config", "disable_config"]

    def status_badge(self, obj: ManufacturerConfiguration) -> str:
        """Display status as colored badge."""
        if obj.is_active:
            return format_html(
                '<span style="color: green;">●</span> Active',
            )
        return format_html(
            '<span style="color: red;">●</span> Inactive',
        )

    status_badge.short_description = "Status"

    def validation_badge(self, obj: ManufacturerConfiguration) -> str:
        """Display validation status as colored badge."""
        if obj.is_valid:
            return format_html(
                '<span style="color: green;">✓ Valid</span>',
            )
        return format_html(
            '<span style="color: red;">✗ Invalid</span>',
        )

    validation_badge.short_description = "Validation"

    def updated_by_name(self, obj: ManufacturerConfiguration) -> str:
        """Display who updated it."""
        if obj.updated_by:
            return obj.updated_by.username
        return "System"

    updated_by_name.short_description = "Updated By"

    def validation_result(self, obj: ManufacturerConfiguration) -> str:
        """Display validation result."""
        if not obj.last_validated:
            return "Not yet validated"

        errors = obj.validation_errors.get("errors", [])
        if not errors:
            return format_html(
                '<span style="color: green;"><strong>✓ Valid</strong></span>'
            )

        error_html = "<br>".join(
            format_html("<li>{}</li>", error) for error in errors
        )
        return format_html(
            '<span style="color: red;"><strong>✗ Invalid</strong></span><ul>{}</ul>',
            error_html,
        )

    validation_result.short_description = "Validation Result"

    def validate_config(
        self, request, queryset: object
    ) -> None:
        """Action to validate configuration."""
        count = 0
        for config in queryset:
            result = config.validate()
            config.save()
            count += 1

        self.message_user(
            request,
            f"Validated {count} configuration(s)",
            messages.SUCCESS,
        )

    validate_config.short_description = "Validate selected configurations"

    def apply_config(self, request, queryset: object) -> None:
        """Action to apply configuration."""
        applied = 0
        failed = 0

        for config in queryset:
            if config.apply_to_service():
                applied += 1
            else:
                failed += 1

        if applied:
            self.message_user(
                request,
                f"Applied {applied} configuration(s)",
                messages.SUCCESS,
            )
        if failed:
            self.message_user(
                request,
                f"Failed to apply {failed} configuration(s)",
                messages.ERROR,
            )

    apply_config.short_description = "Apply selected configurations to service"

    def enable_config(self, request, queryset: object) -> None:
        """Action to enable configuration."""
        count = queryset.update(is_active=True)
        self.message_user(
            request,
            f"Enabled {count} configuration(s)",
            messages.SUCCESS,
        )

    enable_config.short_description = "Enable selected configurations"

    def disable_config(self, request, queryset: object) -> None:
        """Action to disable configuration."""
        count = queryset.update(is_active=False)
        self.message_user(
            request,
            f"Disabled {count} configuration(s)",
            messages.SUCCESS,
        )

    disable_config.short_description = "Disable selected configurations"


@admin.register(ConfigurationAuditLog)
class ConfigurationAuditLogAdmin(admin.ModelAdmin):
    """Admin for ConfigurationAuditLog."""

    list_display = (
        "configuration_code",
        "get_action_badge",
        "created_by_name",
        "result_badge",
        "created_at",
    )
    list_filter = ("action", "result", "created_at")
    search_fields = ("configuration__code", "created_by__username")
    readonly_fields = (
        "configuration",
        "action",
        "created_by",
        "created_at",
        "old_values",
        "new_values",
        "result",
        "error_message",
    )
    date_hierarchy = "created_at"

    def get_action_badge(self, obj: ConfigurationAuditLog) -> str:
        """Display action as colored badge."""
        colors = {
            "create": "#0066cc",
            "update": "#ff9900",
            "delete": "#cc0000",
            "validate": "#00cc00",
            "apply": "#9900cc",
            "test": "#0099cc",
        }
        color = colors.get(obj.action, "#666666")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_action_display(),
        )

    get_action_badge.short_description = "Action"

    def configuration_code(self, obj: ConfigurationAuditLog) -> str:
        """Display configuration code with link."""
        url = reverse(
            "admin:micboard_manufacturerconfiguration_change",
            args=[obj.configuration.id],
        )
        return format_html(
            '<a href="{}">{}</a>',
            url,
            obj.configuration.code,
        )

    configuration_code.short_description = "Configuration"

    def created_by_name(self, obj: ConfigurationAuditLog) -> str:
        """Display created by user."""
        if obj.created_by:
            return obj.created_by.username
        return "System"

    created_by_name.short_description = "Created By"

    def result_badge(self, obj: ConfigurationAuditLog) -> str:
        """Display result as colored badge."""
        if obj.result == "success":
            return format_html(
                '<span style="color: green;">✓ Success</span>',
            )
        return format_html(
            '<span style="color: red;">✗ Failed</span>',
        )

    result_badge.short_description = "Result"


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
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

    def activity_type_badge(self, obj: ActivityLog) -> str:
        """Display activity type as colored badge."""
        colors = {
            "crud": "#0066cc",
            "service": "#ff9900",
            "sync": "#00cc00",
            "config": "#9900cc",
            "discovery": "#00cccc",
            "alert": "#cc0000",
        }
        color = colors.get(obj.activity_type, "#666666")
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_activity_type_display(),
        )

    activity_type_badge.short_description = "Type"

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
            "warning": "#ff9900",
        }
        color = colors.get(obj.operation, "#666666")
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_operation_display(),
        )

    operation_badge.short_description = "Operation"

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

    user_name.short_description = "User/Service"

    def status_badge(self, obj: ActivityLog) -> str:
        """Display status as colored badge."""
        colors = {
            "success": "#00cc00",
            "failed": "#cc0000",
            "warning": "#ff9900",
        }
        color = colors.get(obj.status, "#666666")
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.status.upper(),
        )

    status_badge.short_description = "Status"


@admin.register(ServiceSyncLog)
class ServiceSyncLogAdmin(admin.ModelAdmin):
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

    def service_name(self, obj: ServiceSyncLog) -> str:
        """Display service name."""
        return obj.service.name

    service_name.short_description = "Service"

    def sync_type_badge(self, obj: ServiceSyncLog) -> str:
        """Display sync type as badge."""
        colors = {
            "full": "#0066cc",
            "incremental": "#00cc00",
            "health_check": "#ff9900",
        }
        color = colors.get(obj.sync_type, "#666666")
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_sync_type_display(),
        )

    sync_type_badge.short_description = "Type"

    def status_badge(self, obj: ServiceSyncLog) -> str:
        """Display status as colored badge."""
        colors = {
            "success": "#00cc00",
            "partial": "#ff9900",
            "failed": "#cc0000",
        }
        color = colors.get(obj.status, "#666666")
        return format_html(
            '<span style="background: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.status.upper(),
        )

    status_badge.short_description = "Status"

    def duration(self, obj: ServiceSyncLog) -> str:
        """Display sync duration."""
        seconds = obj.duration_seconds()
        if seconds < 60:
            return f"{seconds}s"
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}m {seconds}s"

    duration.short_description = "Duration"

    def duration_display(self, obj: ServiceSyncLog) -> str:
        """Display duration for detail view."""
        return f"{obj.duration_seconds()} seconds"

    duration_display.short_description = "Duration"
