"""Django admin interface for settings management."""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.forms import ModelForm
from django.utils.html import format_html

from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.settings import Setting, SettingDefinition


class SettingDefinitionForm(ModelForm):
    """Form for SettingDefinition with field type validation."""

    class Meta:
        model = SettingDefinition
        fields = [
            "key",
            "label",
            "description",
            "scope",
            "setting_type",
            "default_value",
            "choices_json",
            "required",
            "is_active",
        ]

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()

        # Validate choices for TYPE_CHOICES
        if cleaned_data.get("setting_type") == SettingDefinition.TYPE_CHOICES:
            if not cleaned_data.get("choices_json"):
                self.add_error("setting_type", "Choices JSON is required for dropdown type")

        return cleaned_data


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
        """Display parsed default value."""
        try:
            parsed = obj.parse_value(obj.default_value)
            return str(parsed)
        except Exception as e:
            return format_html("<em style='color: red;'>Parse Error: {}</em>", e)


class SettingValueForm(ModelForm):
    """Form for Setting values with smart field generation."""

    class Meta:
        model = Setting
        fields = ["definition", "organization", "site", "manufacturer", "value"]

    def __init__(self, *args, **kwargs):
        """Initialize value form and adjust help text based on definition type."""
        super().__init__(*args, **kwargs)

        # Make value a textarea but use smaller size for boolean/integer
        if self.instance and self.instance.definition:
            defn = self.instance.definition
            if defn.setting_type == SettingDefinition.TYPE_BOOLEAN:
                self.fields["value"].help_text = "Enter: true, false, 1, 0, yes, no"
            elif defn.setting_type == SettingDefinition.TYPE_INTEGER:
                self.fields["value"].help_text = "Enter an integer value"
            elif defn.setting_type == SettingDefinition.TYPE_CHOICES:
                choices = [(k, v) for k, v in defn.choices_json.items()]
                self.fields["value"].help_text = f"Choose from: {choices}"

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        definition = cleaned_data.get("definition")
        value = cleaned_data.get("value")

        if definition and value:
            # Validate value can be parsed
            try:
                definition.parse_value(value)
            except Exception as e:
                self.add_error("value", f"Invalid value for type {definition.setting_type}: {e}")

        return cleaned_data


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
        "organization",
        "site",
        "manufacturer",
    )
    search_fields = ("definition__key", "definition__label", "value")
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
                "fields": ("organization", "site", "manufacturer"),
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

    @admin.display(description="Setting")
    def setting_key(self, obj: Setting) -> str:
        return f"{obj.definition.key} ({obj.definition.label})"

    @admin.display(description="Value")
    def value_display(self, obj: Setting) -> str:
        value_str = obj.value[:50]
        if len(obj.value) > 50:
            value_str += "..."
        return value_str

    @admin.display(description="Scope")
    def scope_display(self, obj: Setting) -> str:
        if obj.organization:
            return f"Org: {obj.organization.name}"
        elif obj.site:
            return f"Site: {obj.site.name}"
        elif obj.manufacturer:
            return f"Mfg: {obj.manufacturer.name}"
        return "Global"

    @admin.display(description="Type")
    def definition_type(self, obj: Setting) -> str:
        return obj.definition.get_setting_type_display()

    @admin.display(description="Parsed Value")
    def parsed_value_display(self, obj: Setting) -> str:
        """Display the parsed value."""
        try:
            parsed = obj.get_parsed_value()
            return f"<code>{repr(parsed)}</code>"
        except Exception as e:
            return format_html("<em style='color: red;'>Parse Error: {}</em>", e)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        if change:
            messages.success(request, f"✅ Setting '{obj.definition.label}' updated")
        else:
            messages.success(request, f"✅ New setting '{obj.definition.label}' created")

        # Invalidate cache
        from micboard.services.settings_registry import SettingsRegistry

        SettingsRegistry.invalidate_cache(obj.definition.key)
