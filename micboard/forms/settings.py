"""Forms for bulk configuration of settings."""

from __future__ import annotations

from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from micboard.models.multitenancy import Organization, Site
from micboard.models.settings import Setting, SettingDefinition
from micboard.services.settings_registry import SettingsRegistry


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

    organization = forms.ModelChoiceField(
        queryset=Organization.objects.all(),
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

    manufacturer = forms.ModelChoiceField(
        queryset=None,  # Set in __init__
        required=False,
        label="Manufacturer",
        help_text="Only shown for manufacturer-scoped settings",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Populate manufacturer choices
        from micboard.models.discovery import Manufacturer

        self.fields["manufacturer"].queryset = Manufacturer.objects.all()

        # Load setting definitions dynamically
        self._add_setting_fields()

    def _add_setting_fields(self):
        """Dynamically add fields for each active setting definition."""
        definitions = SettingDefinition.objects.filter(is_active=True).order_by("key")

        for defn in definitions:
            field_name = f"setting_{defn.id}"
            help_text = defn.description or f"Type: {defn.get_setting_type_display()}"

            if defn.setting_type == SettingDefinition.TYPE_BOOLEAN:
                self.fields[field_name] = forms.BooleanField(
                    required=False,
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
                choices = [(k, v) for k, v in defn.choices_json.items()]
                self.fields[field_name] = forms.ChoiceField(
                    choices=[("", "---")] + choices,
                    required=False,
                    label=defn.label,
                    help_text=help_text,
                )
            else:  # String, JSON
                self.fields[field_name] = forms.CharField(
                    required=False,
                    label=defn.label,
                    help_text=help_text,
                    widget=forms.Textarea(attrs={"rows": 2}),
                )

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        scope = cleaned_data.get("scope")

        # Validate scope-specific fields
        if scope == SettingDefinition.SCOPE_ORGANIZATION:
            if not cleaned_data.get("organization"):
                raise ValidationError("Organization is required for organization-scoped settings")
        elif scope == SettingDefinition.SCOPE_SITE:
            if not cleaned_data.get("site"):
                raise ValidationError("Site is required for site-scoped settings")
        elif scope == SettingDefinition.SCOPE_MANUFACTURER:
            if not cleaned_data.get("manufacturer"):
                raise ValidationError("Manufacturer is required for manufacturer-scoped settings")

        return cleaned_data

    def save_settings(self) -> dict[str, str]:
        """Save all configured settings and return results."""
        if not self.is_valid():
            raise ValidationError("Form is not valid")

        results = {"saved": 0, "errors": []}
        scope = self.cleaned_data["scope"]
        organization = self.cleaned_data.get("organization")
        site = self.cleaned_data.get("site")
        manufacturer = self.cleaned_data.get("manufacturer")

        # Get all setting definitions
        definitions = SettingDefinition.objects.filter(is_active=True)

        for defn in definitions:
            field_name = f"setting_{defn.id}"
            value = self.cleaned_data.get(field_name)

            # Skip empty values
            if value == "" or value is None:
                continue

            try:
                # Serialize value according to type
                serialized = defn.serialize_value(value)

                # Get or create Setting
                setting, created = Setting.objects.update_or_create(
                    definition=defn,
                    organization=organization
                    if scope == SettingDefinition.SCOPE_ORGANIZATION
                    else None,
                    site=site if scope == SettingDefinition.SCOPE_SITE else None,
                    manufacturer=manufacturer
                    if scope == SettingDefinition.SCOPE_MANUFACTURER
                    else None,
                    defaults={"value": serialized},
                )

                results["saved"] += 1

                # Invalidate cache
                SettingsRegistry.invalidate_cache(defn.key)

            except Exception as e:
                results["errors"].append(f"Error setting {defn.label}: {e}")

        return results


class ManufacturerSettingsForm(forms.Form):
    """Quick-access form for configuring manufacturer-specific settings."""

    manufacturer = forms.ModelChoiceField(
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
    supports_discovery_ips = forms.BooleanField(
        label="Supports Discovery IPs",
        required=False,
    )
    supports_health_check = forms.BooleanField(
        label="Supports Health Check",
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from micboard.models.discovery import Manufacturer

        self.fields["manufacturer"].queryset = Manufacturer.objects.all()

    def save_settings(self) -> dict[str, str]:
        """Save manufacturer configuration."""
        if not self.is_valid():
            raise ValidationError("Form is not valid")

        manufacturer = self.cleaned_data["manufacturer"]
        results = {"saved": 0, "errors": []}

        # Map form fields to setting keys
        field_mapping = {
            "battery_good_level": "battery_good_level",
            "battery_low_level": "battery_low_level",
            "battery_critical_level": "battery_critical_level",
            "health_check_interval": "health_check_interval",
            "api_timeout": "api_timeout",
            "device_max_requests_per_call": "device_max_requests_per_call",
            "supports_discovery_ips": "supports_discovery_ips",
            "supports_health_check": "supports_health_check",
        }

        for field_name, setting_key in field_mapping.items():
            value = self.cleaned_data.get(field_name)

            # Skip empty values
            if value == "" or value is None:
                continue

            try:
                # Get definition
                defn = SettingDefinition.objects.get(key=setting_key)

                # Serialize
                serialized = defn.serialize_value(value)

                # Save
                Setting.objects.update_or_create(
                    definition=defn,
                    manufacturer=manufacturer,
                    organization=None,
                    site=None,
                    defaults={"value": serialized},
                )

                results["saved"] += 1
                SettingsRegistry.invalidate_cache(setting_key)

            except SettingDefinition.DoesNotExist:
                results["errors"].append(f"Setting definition not found for {setting_key}")
            except Exception as e:
                results["errors"].append(f"Error saving {field_name}: {e}")

        return results
