"""Django admin interface for settings management."""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.forms import ModelForm
from django.utils.html import format_html

from micboard.admin.mixins import MicboardModelAdmin
from micboard.forms.settings_admin import SettingDefinitionForm, SettingValueForm
from micboard.models.settings.registry import Setting, SettingDefinition
from micboard.services.settings.presentation_service import settings_presentation
from micboard.services.settings.visibility_service import settings_visibility
from micboard.services.shared.settings_registry import SettingsRegistry


def _without_raw_field(
    fieldsets: tuple[Any, ...],
    *,
    raw_field: str,
) -> list[tuple[Any, dict[str, Any]]]:
    """Remove one raw-value field from readonly admin fieldsets."""
    safe_fieldsets: list[tuple[Any, dict[str, Any]]] = []
    for title, options in fieldsets:
        safe_options = dict(options)
        safe_options["fields"] = tuple(
            field_name for field_name in options["fields"] if field_name != raw_field
        )
        safe_fieldsets.append((title, safe_options))
    return safe_fieldsets


@admin.register(SettingDefinition)
class SettingDefinitionAdmin(MicboardModelAdmin):
    """Admin for defining available settings."""

    form = SettingDefinitionForm
    list_display = (
        "key",
        "label",
        "scope_badge",
        "type_badge",
        "required_badge",
        "is_active_badge",
    )
    list_filter = ("scope", "setting_type", "required", "is_active")
    search_fields = ("key", "label", "description")
    readonly_fields = ("created_at", "updated_at", "default_value_display")

    fieldsets = (
        (
            "Setting Identity",
            {
                "fields": ("key", "label", "description"),
                "description": "Unique identifier and human-readable label for this setting.",
            },
        ),
        (
            "Scope & Type",
            {
                "fields": ("scope", "setting_type", "choices_json"),
                "description": (
                    "Scope determines where this setting can be configured. "
                    "Type determines how values are stored and parsed."
                ),
            },
        ),
        (
            "Default & Validation",
            {
                "fields": ("default_value", "required", "default_value_display"),
                "description": "Default value used if no specific setting is configured.",
            },
        ),
        (
            "Status",
            {
                "fields": ("is_active", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def get_fieldsets(self, request: Any, obj: SettingDefinition | None = None) -> Any:
        """Hide raw defaults from view-only detail pages."""
        if obj is not None and not self.has_change_permission(request, obj):
            return _without_raw_field(self.fieldsets, raw_field="default_value")
        return super().get_fieldsets(request, obj)

    def has_import_permission(self, request: Any) -> bool:
        """Disable generic imports that bypass secret-safe forms."""
        return False

    def has_export_permission(self, request: Any) -> bool:
        """Disable generic exports that would reveal stored defaults."""
        return False

    def save_model(
        self,
        request: Any,
        obj: SettingDefinition,
        form: ModelForm,
        change: bool,
    ) -> None:
        """Persist definition metadata and invalidate every derived cache entry."""
        previous_key = None
        if change and obj.pk:
            previous_key = (
                SettingDefinition.objects.filter(pk=obj.pk).values_list("key", flat=True).first()
            )
        super().save_model(request, obj, form, change)
        for key in {previous_key, obj.key}:
            if key is not None:
                SettingsRegistry.invalidate_definition(key)

    def delete_model(self, request: Any, obj: SettingDefinition) -> None:
        """Delete one definition and invalidate its cached metadata and value."""
        key = obj.key
        super().delete_model(request, obj)
        SettingsRegistry.invalidate_definition(key)

    def delete_queryset(self, request: Any, queryset: QuerySet[SettingDefinition]) -> None:
        """Invalidate each definition removed by the bulk-delete action."""
        keys = set(queryset.values_list("key", flat=True))
        super().delete_queryset(request, queryset)
        for key in keys:
            SettingsRegistry.invalidate_definition(key)

    @admin.display(description="Scope")
    def scope_badge(self, obj: SettingDefinition) -> str:
        """Display scope as badge."""
        colors = {
            SettingDefinition.SCOPE_GLOBAL: "blue",
            SettingDefinition.SCOPE_ORGANIZATION: "purple",
            SettingDefinition.SCOPE_SITE: "green",
            SettingDefinition.SCOPE_MANUFACTURER: "orange",
        }
        color = colors.get(obj.scope, "gray")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.get_scope_display(),
        )

    @admin.display(description="Type")
    def type_badge(self, obj: SettingDefinition) -> str:
        """Display type as badge."""
        return obj.get_setting_type_display()

    @admin.display(boolean=True, description="Required")
    def required_badge(self, obj: SettingDefinition) -> bool:
        return obj.required

    @admin.display(boolean=True, description="Active")
    def is_active_badge(self, obj: SettingDefinition) -> bool:
        return obj.is_active

    @admin.display(description="Default Value")
    def default_value_display(self, obj: SettingDefinition) -> str:
        """Display only explicitly safe default values."""
        if settings_presentation.is_sensitive_definition(obj):
            return settings_presentation.format_value(obj, obj.default_value)
        try:
            parsed = obj.parse_value(obj.default_value)
            return settings_presentation.format_value(obj, parsed)
        except Exception as e:
            return format_html("<em style='color: red;'>Parse Error: {}</em>", e)


@admin.register(Setting)
class SettingAdmin(MicboardModelAdmin):
    """Admin for configuring setting values."""

    form = SettingValueForm
    list_display = (
        "setting_key",
        "value_display",
        "scope_display",
        "definition_type",
    )
    list_filter = (
        "definition__scope",
        "definition__setting_type",
        "site",
    )
    search_fields = ("definition__key", "definition__label")
    readonly_fields = ("created_at", "updated_at", "parsed_value_display")

    fieldsets = (
        (
            "Setting",
            {
                "fields": ("definition",),
                "description": "Which setting to configure.",
            },
        ),
        (
            "Scope",
            {
                "fields": ("organization_id", "site", "manufacturer_id"),
                "description": (
                    "Select the scope where this setting applies. "
                    "Leave all empty for global. "
                    "Only one should typically be set."
                ),
            },
        ),
        (
            "Value",
            {
                "fields": ("value", "parsed_value_display"),
                "description": "The configuration value. Automatically parsed according to type.",
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request: Any) -> Any:
        """Return exact setting rows the current user may manage."""
        queryset: QuerySet[Setting] = admin.ModelAdmin.get_queryset(self, request)
        scope = settings_visibility.for_user(user=request.user)
        return queryset.filter(settings_visibility.build_management_filter(scope)).select_related(
            "definition",
            "site",
        )

    def get_form(self, request: Any, obj: Setting | None = None, **kwargs: Any) -> Any:
        """Inject request user into the setting value form."""
        form = super().get_form(request, obj, **kwargs)
        request_user = request.user

        class UserScopedSettingForm(form):  # type: ignore[misc,valid-type]
            def __init__(self, *args: Any, **form_kwargs: Any) -> None:
                form_kwargs["user"] = request_user
                super().__init__(*args, **form_kwargs)

        return UserScopedSettingForm

    def get_fieldsets(self, request: Any, obj: Setting | None = None) -> Any:
        """Hide raw values from view-only detail pages."""
        if obj is not None and not self.has_change_permission(request, obj):
            return _without_raw_field(self.fieldsets, raw_field="value")
        return super().get_fieldsets(request, obj)

    def has_import_permission(self, request: Any) -> bool:
        """Disable generic imports that bypass tenant-aware validation."""
        return False

    def has_export_permission(self, request: Any) -> bool:
        """Disable generic exports that would reveal stored values."""
        return False

    @admin.display(description="Setting")
    def setting_key(self, obj: Setting) -> str:
        return f"{obj.definition.key} ({obj.definition.label})"

    @admin.display(description="Value")
    def value_display(self, obj: Setting) -> str:
        """Display only explicitly safe stored values."""
        value = settings_presentation.format_value(obj.definition, obj.value)
        if settings_presentation.is_sensitive_definition(obj.definition):
            return value
        return f"{value[:50]}..." if len(value) > 50 else value

    @admin.display(description="Scope")
    def scope_display(self, obj: Setting) -> str:
        if obj.organization_id:
            return f"Org ID: {obj.organization_id}"
        elif obj.site:
            return f"Site: {obj.site.name}"
        elif obj.manufacturer_id:
            return f"Mfg ID: {obj.manufacturer_id}"
        return "Global"

    @admin.display(description="Type")
    def definition_type(self, obj: Setting) -> str:
        return obj.definition.get_setting_type_display()

    @admin.display(description="Parsed Value")
    def parsed_value_display(self, obj: Setting) -> str:
        """Display parsed values only for explicitly safe definitions."""
        if settings_presentation.is_sensitive_definition(obj.definition):
            return settings_presentation.format_value(obj.definition, obj.value)
        try:
            parsed = obj.get_parsed_value()
            return format_html(
                "<code>{}</code>",
                settings_presentation.format_value(obj.definition, repr(parsed)),
            )
        except Exception as e:
            return format_html("<em style='color: red;'>Parse Error: {}</em>", e)

    def save_model(self, request: Any, obj: Setting, form: ModelForm, change: bool) -> None:
        previous_key = None
        if change and obj.pk:
            previous_key = (
                Setting.objects.filter(pk=obj.pk).values_list("definition__key", flat=True).first()
            )
        scope = settings_visibility.for_user(user=request.user)
        if not settings_visibility.can_manage_scope(
            scope,
            organization_id=obj.organization_id,
            site_id=obj.site_id,
            manufacturer_id=obj.manufacturer_id,
        ):
            raise PermissionDenied
        super().save_model(request, obj, form, change)
        if change:
            messages.success(request, f"✅ Setting '{obj.definition.label}' updated")
        else:
            messages.success(request, f"✅ New setting '{obj.definition.label}' created")
        for key in {previous_key, obj.definition.key}:
            if key is not None:
                SettingsRegistry.invalidate_cache(key)

    def delete_model(self, request: Any, obj: Setting) -> None:
        """Delete one value and invalidate its definition's scoped cache entries."""
        key = obj.definition.key
        super().delete_model(request, obj)
        SettingsRegistry.invalidate_cache(key)

    def delete_queryset(self, request: Any, queryset: QuerySet[Setting]) -> None:
        """Invalidate each setting key removed by the bulk-delete action."""
        keys = set(queryset.values_list("definition__key", flat=True))
        super().delete_queryset(request, queryset)
        for key in keys:
            SettingsRegistry.invalidate_cache(key)
