"""Custom admin forms for wireless devices."""

from __future__ import annotations

from django import forms

from micboard.models import WirelessChassis
from micboard.models.device_specs import get_available_band_plans


class WirelessChassisAdminForm(forms.ModelForm):
    """Custom admin form for WirelessChassis with band plan selection."""

    band_plan_selector = forms.ChoiceField(
        required=False,
        label="Select Standard Band Plan",
        help_text="Select a standard band plan to auto-populate frequency range",
    )

    class Meta:
        model = WirelessChassis
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        """Initialize the form and populate dynamic band plan choices."""
        super().__init__(*args, **kwargs)

        # Populate band plan choices based on manufacturer
        if self.instance and self.instance.manufacturer:
            if hasattr(self.instance.manufacturer, "code"):
                mfg_code = self.instance.manufacturer.code.lower()
                band_plans = get_available_band_plans(manufacturer=mfg_code)
                choices = [("", "--- Select band plan ---")] + [
                    (key, name) for key, name in band_plans
                ]
                from typing import cast

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
        band_plan_selector = cleaned_data.get("band_plan_selector")

        # If user selected a standard band plan, copy it to band_plan_name
        if band_plan_selector:
            # Find the full name from choices
            for key, name in self.fields["band_plan_selector"].choices:
                if key == band_plan_selector:
                    cleaned_data["band_plan_name"] = name
                    break

        return cleaned_data
