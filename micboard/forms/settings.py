"""Forms for bulk configuration of settings."""

from __future__ import annotations

from typing import Any, cast

from django import forms
from django.apps import apps
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError

from micboard.models.settings.registry import SettingDefinition
from micboard.services.settings.dtos import (
    SettingsVisibilityScope,
    SettingsWriteRequest,
    SettingWriteItem,
    SettingWriteTarget,
)
from micboard.services.settings.persistence_service import SettingsPersistenceService
from micboard.services.settings.visibility_service import settings_visibility


def _scope_for_user(user: Any | None) -> SettingsVisibilityScope:
    """Return unrestricted scope for trusted non-request callers."""
    if user is None:
        return SettingsVisibilityScope()
    return settings_visibility.for_management_user(user=user)


def _has_choices(identifiers: frozenset[int] | None) -> bool:
    """Return whether one visibility dimension has selectable rows."""
    return identifiers is None or bool(identifiers)


def _optional_boolean_field(*, label: str, help_text: str = "") -> forms.TypedChoiceField:
    """Build an explicit tri-state boolean so omission never overwrites a value."""
    return forms.TypedChoiceField(
        choices=(
            ("", "--- No change ---"),
            ("true", "Enabled"),
            ("false", "Disabled"),
        ),
        coerce=lambda value: value == "true",
        empty_value=None,
        required=False,
        label=label,
        help_text=help_text,
    )


class BulkSettingConfigForm(forms.Form):
    """Form for bulk configuring settings for a specific scope."""

    SCOPE_CHOICES = [
        ("", "--- Select Scope ---"),
        (SettingDefinition.SCOPE_GLOBAL, "Global"),
        (SettingDefinition.SCOPE_ORGANIZATION, "Organization"),
        (SettingDefinition.SCOPE_SITE, "Site"),
        (SettingDefinition.SCOPE_MANUFACTURER, "Manufacturer"),
    ]

    scope = forms.ChoiceField(
        choices=SCOPE_CHOICES,
        required=True,
        label="Configuration Scope",
        help_text="Select where these settings should apply",
    )

    organization: forms.ModelChoiceField = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label="Organization",
        help_text="Only shown for organization-scoped settings",
    )

    site = forms.ModelChoiceField(
        queryset=Site.objects.all(),
        required=False,
        label="Site",
        help_text="Only shown for site-scoped settings",
    )

    manufacturer: forms.ModelChoiceField = forms.ModelChoiceField(
        queryset=None,  # Set in __init__
        required=False,
        label="Manufacturer",
        help_text="Only shown for manufacturer-scoped settings",
    )

    def __init__(self, *args: Any, user: Any | None = None, **kwargs: Any) -> None:
        """Initialize the bulk settings form and dynamically add fields for active definitions."""
        super().__init__(*args, **kwargs)
        self.visibility_scope = _scope_for_user(user)
        unrestricted = settings_visibility.is_unrestricted(self.visibility_scope)

        if apps.is_installed("micboard.multitenancy"):
            from micboard.multitenancy.models import Organization

            organization_selector = cast(forms.ModelChoiceField, self.fields["organization"])
            organizations = Organization._default_manager.all()
            if self.visibility_scope.organization_ids is not None:
                organizations = organizations.filter(pk__in=self.visibility_scope.organization_ids)
            organization_selector.queryset = organizations
        else:
            self.fields.pop("organization")

        site_selector = cast(forms.ModelChoiceField, self.fields["site"])
        sites = Site.objects.all()
        if self.visibility_scope.site_ids is not None:
            sites = sites.filter(pk__in=self.visibility_scope.site_ids)
        site_selector.queryset = sites

        # Populate manufacturer choices
        from micboard.models.discovery.manufacturer import Manufacturer

        selector = cast(forms.ModelChoiceField, self.fields["manufacturer"])
        manufacturers = Manufacturer.objects.all()
        if self.visibility_scope.manufacturer_ids is not None:
            manufacturers = manufacturers.filter(pk__in=self.visibility_scope.manufacturer_ids)
        selector.queryset = manufacturers

        available_scopes = {
            SettingDefinition.SCOPE_GLOBAL: unrestricted,
            SettingDefinition.SCOPE_ORGANIZATION: (
                "organization" in self.fields
                and _has_choices(self.visibility_scope.organization_ids)
            ),
            SettingDefinition.SCOPE_SITE: _has_choices(self.visibility_scope.site_ids),
            SettingDefinition.SCOPE_MANUFACTURER: _has_choices(
                self.visibility_scope.manufacturer_ids
            ),
        }
        scope_selector = cast(forms.ChoiceField, self.fields["scope"])
        scope_selector.choices = [
            choice
            for choice in self.SCOPE_CHOICES
            if not choice[0] or available_scopes.get(choice[0], False)
        ]

        # Load setting definitions dynamically
        self._add_setting_fields()

    def _add_setting_fields(self) -> Any:
        """Dynamically add fields for each active setting definition."""
        definitions = SettingDefinition.objects.filter(is_active=True).order_by("key")
        selected_scope = self.data.get(self.add_prefix("scope")) if self.is_bound else None
        if selected_scope:
            definitions = definitions.filter(scope=selected_scope)

        for defn in definitions:
            field_name = f"setting_{defn.id}"
            help_text = defn.description or f"Type: {defn.get_setting_type_display()}"

            if defn.setting_type == SettingDefinition.TYPE_BOOLEAN:
                self.fields[field_name] = _optional_boolean_field(
                    label=defn.label,
                    help_text=help_text,
                )
            elif defn.setting_type == SettingDefinition.TYPE_INTEGER:
                self.fields[field_name] = forms.IntegerField(
                    required=False,
                    label=defn.label,
                    help_text=help_text,
                )
            elif defn.setting_type == SettingDefinition.TYPE_CHOICES:
                # choices_json may be None; guard and coerce to dict for typing
                choices_dict = defn.choices_json or {}
                choices = [(k, v) for k, v in choices_dict.items()]
                self.fields[field_name] = forms.ChoiceField(
                    choices=[("", "---"), *choices],
                    required=False,
                    label=defn.label,
                    help_text=help_text,
                )
            elif defn.setting_type == SettingDefinition.TYPE_JSON:
                self.fields[field_name] = forms.JSONField(
                    required=False,
                    label=defn.label,
                    help_text=help_text,
                    widget=forms.Textarea(attrs={"rows": 2}),
                )
            else:  # String
                self.fields[field_name] = forms.CharField(
                    required=False,
                    label=defn.label,
                    help_text=help_text,
                    widget=forms.Textarea(attrs={"rows": 2}),
                )

    def clean(self) -> dict[str, Any]:
        cleaned_data: dict[str, Any] = super().clean() or {}
        scope = cleaned_data.get("scope")

        # Validate scope-specific fields
        if scope == SettingDefinition.SCOPE_ORGANIZATION:
            if not apps.is_installed("micboard.multitenancy"):
                raise ValidationError("Organization scope requires the micboard.multitenancy app")
            if not cleaned_data.get("organization"):
                raise ValidationError("Organization is required for organization-scoped settings")
        elif scope == SettingDefinition.SCOPE_SITE:
            if not cleaned_data.get("site"):
                raise ValidationError("Site is required for site-scoped settings")
        elif scope == SettingDefinition.SCOPE_MANUFACTURER:
            if not cleaned_data.get("manufacturer"):
                raise ValidationError("Manufacturer is required for manufacturer-scoped settings")

        organization = cleaned_data.get("organization")
        site = cleaned_data.get("site")
        manufacturer = cleaned_data.get("manufacturer")
        effective_scope = {
            "organization_id": (
                getattr(organization, "pk", None)
                if scope == SettingDefinition.SCOPE_ORGANIZATION
                else None
            ),
            "site_id": getattr(site, "pk", None) if scope == SettingDefinition.SCOPE_SITE else None,
            "manufacturer_id": (
                getattr(manufacturer, "pk", None)
                if scope == SettingDefinition.SCOPE_MANUFACTURER
                else None
            ),
        }
        if not settings_visibility.can_manage_scope(self.visibility_scope, **effective_scope):
            raise ValidationError("You cannot manage settings for the selected scope")

        return cleaned_data

    def save_settings(self) -> dict[str, Any]:
        """Save all configured settings and return results."""
        if not self.is_valid():
            raise ValidationError("Form is not valid")

        scope = self.cleaned_data["scope"]
        organization = self.cleaned_data.get("organization")
        site = self.cleaned_data.get("site")
        manufacturer = self.cleaned_data.get("manufacturer")

        items = [
            SettingWriteItem(
                definition_id=int(field_name.removeprefix("setting_")),
                value=value,
                label=field_name,
            )
            for field_name, value in self.cleaned_data.items()
            if field_name.startswith("setting_") and value not in ("", None)
        ]
        request = SettingsWriteRequest(
            target=SettingWriteTarget(
                scope=scope,
                organization_id=(
                    getattr(organization, "pk", None)
                    if scope == SettingDefinition.SCOPE_ORGANIZATION
                    else None
                ),
                site_id=(
                    getattr(site, "pk", None) if scope == SettingDefinition.SCOPE_SITE else None
                ),
                manufacturer_id=(
                    getattr(manufacturer, "pk", None)
                    if scope == SettingDefinition.SCOPE_MANUFACTURER
                    else None
                ),
            ),
            items=items,
        )
        return SettingsPersistenceService.save(
            request=request,
            visibility_scope=self.visibility_scope,
        ).model_dump()


class ManufacturerSettingsForm(forms.Form):
    """Quick-access form for configuring manufacturer-specific settings."""

    manufacturer: forms.ModelChoiceField = forms.ModelChoiceField(
        queryset=None,  # Set in __init__
        label="Manufacturer",
        help_text="Select which manufacturer to configure",
    )

    # Battery thresholds
    battery_good_level = forms.IntegerField(
        label="Battery Good Level %",
        min_value=0,
        max_value=100,
        required=False,
    )
    battery_low_level = forms.IntegerField(
        label="Battery Low Level %",
        min_value=0,
        max_value=100,
        required=False,
    )
    battery_critical_level = forms.IntegerField(
        label="Battery Critical Level %",
        min_value=0,
        max_value=100,
        required=False,
    )

    # Health check intervals
    health_check_interval = forms.IntegerField(
        label="Health Check Interval (seconds)",
        min_value=10,
        required=False,
    )

    # API timeout
    api_timeout = forms.IntegerField(
        label="API Timeout (seconds)",
        min_value=1,
        required=False,
    )

    # Device max requests
    device_max_requests_per_call = forms.IntegerField(
        label="Max Devices Per Call",
        min_value=1,
        required=False,
    )

    # Feature flags
    supports_discovery_ips = _optional_boolean_field(
        label="Supports Discovery IPs",
    )
    supports_health_check = _optional_boolean_field(
        label="Supports Health Check",
    )

    FIELD_MAPPING = {
        "battery_good_level": "battery_good_level",
        "battery_low_level": "battery_low_level",
        "battery_critical_level": "battery_critical_level",
        "health_check_interval": "health_check_interval",
        "api_timeout": "api_timeout",
        "device_max_requests_per_call": "device_max_requests_per_call",
        "supports_discovery_ips": "supports_discovery_ips",
        "supports_health_check": "supports_health_check",
    }

    def __init__(self, *args: Any, user: Any | None = None, **kwargs: Any) -> None:
        """Initialize the manufacturer settings form and load manufacturer queryset."""
        super().__init__(*args, **kwargs)
        self.visibility_scope = _scope_for_user(user)

        from micboard.models.discovery.manufacturer import Manufacturer

        selector = cast(forms.ModelChoiceField, self.fields["manufacturer"])
        manufacturers = Manufacturer.objects.all()
        if self.visibility_scope.manufacturer_ids is not None:
            manufacturers = manufacturers.filter(pk__in=self.visibility_scope.manufacturer_ids)
        selector.queryset = manufacturers

    def save_settings(self) -> dict[str, Any]:
        """Save manufacturer configuration."""
        if not self.is_valid():
            raise ValidationError("Form is not valid")

        manufacturer = self.cleaned_data["manufacturer"]
        items = [
            SettingWriteItem(key=setting_key, value=value, label=field_name)
            for field_name, setting_key in self.FIELD_MAPPING.items()
            if (value := self.cleaned_data.get(field_name)) not in ("", None)
        ]
        request = SettingsWriteRequest(
            target=SettingWriteTarget(
                scope=SettingDefinition.SCOPE_MANUFACTURER,
                manufacturer_id=manufacturer.pk,
            ),
            items=items,
        )
        try:
            return SettingsPersistenceService.save(
                request=request,
                visibility_scope=self.visibility_scope,
            ).model_dump()
        except ValidationError as exc:
            raise ValidationError(
                "You cannot manage settings for the selected manufacturer"
            ) from exc
