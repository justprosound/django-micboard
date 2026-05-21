"""Django admin configuration for configuration models."""

from __future__ import annotations

from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from micboard.admin.mixins import MicboardModelAdmin
from micboard.models import ConfigurationAuditLog, ManufacturerConfiguration


@admin.register(ManufacturerConfiguration)
class ManufacturerConfigurationAdmin(MicboardModelAdmin):
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
    list_select_related = ("updated_by",)
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

    @admin.display(description="Status")
    def status_badge(self, obj: ManufacturerConfiguration) -> str:
        """Display status as colored badge."""
        if obj.is_active:
            return format_html(
                '<span style="color: green;">\u25cf</span> Active',
            )
        return format_html(
            '<span style="color: red;">\u25cf</span> Inactive',
        )

    @admin.display(description="Validation")
    def validation_badge(self, obj: ManufacturerConfiguration) -> str:
        """Display validation status as colored badge."""
        if obj.is_valid:
            return format_html(
                '<span style="color: green;">\u2713 Valid</span>',
            )
        return format_html(
            '<span style="color: red;">\u2717 Invalid</span>',
        )

    @admin.display(description="Updated By")
    def updated_by_name(self, obj: ManufacturerConfiguration) -> str:
        """Display who updated it."""
        if obj.updated_by:
            return obj.updated_by.username
        return "System"

    @admin.display(description="Validation Result")
    def validation_result(self, obj: ManufacturerConfiguration) -> str:
        """Display validation result."""
        if not obj.last_validated:
            return "Not yet validated"

        errors = obj.validation_errors.get("errors", [])
        if not errors:
            return "\u2713 Valid"

        error_list = "; ".join(str(error) for error in errors[:3])
        if len(errors) > 3:
            error_list += f" (+{len(errors) - 3} more)"
        return f"\u2717 Invalid: {error_list}"

    @admin.action(description="Validate selected configurations")
    def validate_config(self, request, queryset) -> None:
        """Action to validate configuration."""
        count = 0
        for config in queryset:
            _ = config.validate()
            config.save()
            count += 1

        self.message_user(
            request,
            f"Validated {count} configuration(s)",
            messages.SUCCESS,
        )

    @admin.action(description="Apply selected configurations to service")
    def apply_config(self, request, queryset) -> None:
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

    @admin.action(description="Enable selected configurations")
    def enable_config(self, request, queryset) -> None:
        """Action to enable configuration."""
        count = queryset.update(is_active=True)
        self.message_user(
            request,
            f"Enabled {count} configuration(s)",
            messages.SUCCESS,
        )

    @admin.action(description="Disable selected configurations")
    def disable_config(self, request, queryset) -> None:
        """Action to disable configuration."""
        count = queryset.update(is_active=False)
        self.message_user(
            request,
            f"Disabled {count} configuration(s)",
            messages.SUCCESS,
        )


@admin.register(ConfigurationAuditLog)
class ConfigurationAuditLogAdmin(MicboardModelAdmin):
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
    list_select_related = ("configuration", "created_by")
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

    @admin.display(description="Action")
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

    @admin.display(description="Configuration")
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

    @admin.display(description="Created By")
    def created_by_name(self, obj: ConfigurationAuditLog) -> str:
        """Display created by user."""
        if obj.created_by:
            return obj.created_by.username
        return "System"

    @admin.display(description="Result")
    def result_badge(self, obj: ConfigurationAuditLog) -> str:
        """Display result as colored badge."""
        if obj.result == "success":
            return format_html(
                '<span style="color: green;">\u2713 Success</span>',
            )
        return format_html(
            '<span style="color: red;">\u2717 Failed</span>',
        )
