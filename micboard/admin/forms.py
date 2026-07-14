"""Custom admin forms for wireless devices."""

from __future__ import annotations

from typing import cast

from django import forms

from micboard.models.band_plans import get_available_band_plans
from micboard.models.hardware.wireless_chassis import WirelessChassis


class WirelessChassisAdminForm(forms.ModelForm):
    """Custom admin form for WirelessChassis with band plan selection."""

    band_plan_selector = forms.ChoiceField(
        required=False,
        label="Select Standard Band Plan",
        help_text="Select a standard band plan to auto-populate frequency range",
    )

    class Meta:
        model = WirelessChassis
        fields = [
            "role",
            "manufacturer",
            "api_device_id",
            "serial_number",
            "mac_address",
            "model",
            "name",
            "fqdn",
            "description",
            "protocol_family",
            "wmas_capable",
            "licensed_resource_count",
            "ip",
            "subnet_mask",
            "gateway",
            "network_mode",
            "interface_id",
            "mac_address_secondary",
            "ip_address_secondary",
            "firmware_version",
            "hosted_firmware_version",
            "location",
            "order",
            "status",
            "last_seen",
            "is_online",
            "last_online_at",
            "last_offline_at",
            "total_uptime_minutes",
            "max_channels",
            "dante_capable",
            "band_plan_min_mhz",
            "band_plan_max_mhz",
            "band_plan_name",
        ]

    def __init__(self, *args, **kwargs):
        """Initialize the form and populate dynamic band plan choices."""
        super().__init__(*args, **kwargs)

        # Populate band plan choices based on manufacturer
        if self.instance.manufacturer_id:
            manufacturer = self.instance.manufacturer
            if hasattr(manufacturer, "code"):
                mfg_code = manufacturer.code.lower()
                band_plans = get_available_band_plans(manufacturer=mfg_code)
                choices = [("", "--- Select band plan ---")] + [
                    (key, name) for key, name in band_plans
                ]
                selector = cast(forms.ChoiceField, self.fields["band_plan_selector"])
                selector.choices = choices

                # Pre-select current band plan if it matches
                if self.instance.band_plan_name:
                    band_key = (
                        self.instance.band_plan_name.lower().replace(" ", "_").replace("-", "_")
                    )
                    if any(key == band_key for key, _ in band_plans):
                        selector.initial = band_key
        else:
            # No manufacturer yet - disable band plan selection
            selector = cast(forms.ChoiceField, self.fields["band_plan_selector"])
            selector.choices = [("", "--- Select manufacturer first ---")]
            selector.disabled = True

        # Add help text to make workflow clear
        self.fields["band_plan_name"].help_text = (
            "Either select from standard band plans above, or enter a custom name "
            "(frequencies will be parsed from format like 'G50 (470-534 MHz)')"
        )
        self.fields[
            "band_plan_min_mhz"
        ].help_text = "Auto-populated when standard band plan selected (can be manually overridden)"
        self.fields[
            "band_plan_max_mhz"
        ].help_text = "Auto-populated when standard band plan selected (can be manually overridden)"

    def clean(self):
        """Handle band plan selection and validate."""
        cleaned_data = super().clean()
        if cleaned_data is None:
            cleaned_data = {}
        band_plan_selector = cleaned_data.get("band_plan_selector")

        # If user selected a standard band plan, copy it to band_plan_name
        if band_plan_selector:
            # Find the full name from choices
            selector = cast(forms.ChoiceField, self.fields["band_plan_selector"])
            # cast avoids django-stubs union-attr issue with ChoiceField.choices
            selector_choices = cast(list, selector.choices)
            for key, name in selector_choices:
                if key == band_plan_selector:
                    cleaned_data["band_plan_name"] = name
                    break

        return cleaned_data
