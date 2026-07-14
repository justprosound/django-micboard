"""Forms used by the standard Django settings administration."""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.apps import apps
from django.contrib.sites.models import Site
from django.db.models import Q
from django.forms import ModelForm

from micboard.models.settings.registry import Setting, SettingDefinition
from micboard.services.settings.dtos import SettingsVisibilityScope
from micboard.services.settings.presentation_service import settings_presentation
from micboard.services.settings.visibility_service import settings_visibility


def _scope_for_user(user: Any | None) -> SettingsVisibilityScope:
    """Return unrestricted scope for trusted non-request form callers."""
    if user is None:
        return SettingsVisibilityScope()
    return settings_visibility.for_user(user=user)


class SettingDefinitionForm(ModelForm):
    """Validate setting definitions while keeping sensitive defaults write-only."""

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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Use a non-rendering widget for unknown or sensitive defaults."""
        super().__init__(*args, **kwargs)
        key = self.instance.key
        if self.is_bound:
            key = str(self.data.get(self.add_prefix("key"), key))
        if settings_presentation.is_key_sensitive(key):
            default_field = self.fields["default_value"]
            default_field.widget = forms.PasswordInput(render_value=False)
            default_field.required = self.instance.pk is None

    def clean(self) -> dict[str, Any]:
        """Preserve omitted secrets and enforce choice-definition metadata."""
        cleaned_data = super().clean() or {}

        key = str(cleaned_data.get("key", self.instance.key))
        if (
            self.instance.pk
            and settings_presentation.is_key_sensitive(key)
            and not cleaned_data.get("default_value")
        ):
            cleaned_data["default_value"] = self.instance.default_value

        if cleaned_data.get(
            "setting_type"
        ) == SettingDefinition.TYPE_CHOICES and not cleaned_data.get("choices_json"):
            self.add_error("setting_type", "Choices JSON is required for dropdown type")

        return cleaned_data


class SettingValueForm(ModelForm):
    """Validate setting values against their type and authorized target scope."""

    class Meta:
        model = Setting
        fields = ["definition", "organization_id", "site", "manufacturer_id", "value"]

    def __init__(self, *args: Any, user: Any | None = None, **kwargs: Any) -> None:
        """Scope selectable targets and prevent existing secrets from rendering."""
        super().__init__(*args, **kwargs)
        self.visibility_scope = _scope_for_user(user)
        self._scope_target_fields()

        definition = self._selected_definition()
        sensitive = definition is None or settings_presentation.is_sensitive_definition(definition)
        if sensitive:
            value_field = self.fields["value"]
            value_field.widget = forms.PasswordInput(render_value=False)
            value_field.required = self.instance.pk is None

        if definition is not None:
            if definition.setting_type == SettingDefinition.TYPE_BOOLEAN:
                self.fields["value"].help_text = "Enter: true, false, 1, 0, yes, no"
            elif definition.setting_type == SettingDefinition.TYPE_INTEGER:
                self.fields["value"].help_text = "Enter an integer value"
            elif definition.setting_type == SettingDefinition.TYPE_CHOICES:
                choices = [(key, label) for key, label in definition.choices_json.items()]
                self.fields["value"].help_text = f"Choose from: {choices}"

    def _selected_definition(self) -> SettingDefinition | None:
        """Resolve the selected definition without trusting a submitted value."""
        definition_id = self.instance.definition_id
        if self.is_bound:
            definition_id = self.data.get(self.add_prefix("definition"), definition_id)
        if not definition_id:
            return None
        return SettingDefinition.objects.filter(pk=definition_id).first()

    def _scope_target_fields(self) -> None:
        """Replace raw tenant IDs with choices from the user's exact scope."""
        definition_selector = cast(forms.ModelChoiceField, self.fields["definition"])
        definitions = SettingDefinition.objects.filter(is_active=True)
        if self.instance.definition_id is not None:
            definitions = SettingDefinition.objects.filter(
                Q(is_active=True) | Q(pk=self.instance.definition_id)
            )
        definition_selector.queryset = definitions

        organization_choices: list[tuple[int | str, str]] = [("", "---------")]
        if apps.is_installed("micboard.multitenancy"):
            from micboard.multitenancy.models import Organization

            organizations = Organization._default_manager.all()
            if self.visibility_scope.organization_ids is not None:
                organizations = organizations.filter(pk__in=self.visibility_scope.organization_ids)
            organization_choices.extend(organizations.values_list("pk", "name"))
        self.fields["organization_id"] = forms.TypedChoiceField(
            choices=organization_choices,
            coerce=int,
            empty_value=None,
            required=False,
            label="Organization",
        )

        site_selector = cast(forms.ModelChoiceField, self.fields["site"])
        sites = Site.objects.all()
        if self.visibility_scope.site_ids is not None:
            sites = sites.filter(pk__in=self.visibility_scope.site_ids)
        site_selector.queryset = sites

        from micboard.models.discovery.manufacturer import Manufacturer

        manufacturers = Manufacturer.objects.all()
        if self.visibility_scope.manufacturer_ids is not None:
            manufacturers = manufacturers.filter(pk__in=self.visibility_scope.manufacturer_ids)
        manufacturer_choices: list[tuple[int | str, str]] = [("", "---------")]
        manufacturer_choices.extend(manufacturers.values_list("pk", "name"))
        self.fields["manufacturer_id"] = forms.TypedChoiceField(
            choices=manufacturer_choices,
            coerce=int,
            empty_value=None,
            required=False,
            label="Manufacturer",
        )

    def clean(self) -> dict[str, Any]:
        """Validate parsing, definition scope, and caller authorization."""
        cleaned_data = super().clean() or {}
        definition = cleaned_data.get("definition")
        value = cleaned_data.get("value")

        if (
            definition
            and settings_presentation.is_sensitive_definition(definition)
            and self.instance.pk
            and not value
        ):
            value = self.instance.value
            cleaned_data["value"] = value

        if definition and value:
            try:
                definition.parse_value(value)
            except Exception:
                self.add_error(
                    "value",
                    f"Invalid value for type {definition.setting_type}; details redacted.",
                )

        selected_scope = {
            "organization_id": cleaned_data.get("organization_id"),
            "site_id": getattr(cleaned_data.get("site"), "pk", None),
            "manufacturer_id": cleaned_data.get("manufacturer_id"),
        }
        if definition and not settings_visibility.matches_definition_scope(
            definition_scope=definition.scope,
            **selected_scope,
        ):
            raise forms.ValidationError(
                "The selected target does not match this setting definition's scope"
            )

        if not settings_visibility.can_manage_scope(self.visibility_scope, **selected_scope):
            raise forms.ValidationError("You cannot manage settings for the selected scope")

        return cleaned_data
