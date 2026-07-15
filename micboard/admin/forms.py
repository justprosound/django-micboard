"""Custom admin forms for wireless devices."""

from __future__ import annotations

from typing import cast

from django import forms
from django.core.exceptions import PermissionDenied

from micboard.exceptions import OrganizationDeviceQuotaExceededError
from micboard.models.band_plans import get_available_band_plans
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.hardware.chassis_admin_service import (
    CHASSIS_ADMIN_WRITE_FIELDS,
    ChassisAdminService,
)
from micboard.services.hardware.wireless_chassis_persistence_service import (
    WirelessChassisPersistenceService,
)


class WirelessChassisAdminForm(forms.ModelForm):
    """Custom admin form for WirelessChassis with band plan selection."""

    scope_user = None

    band_plan_selector = forms.ChoiceField(
        required=False,
        label="Select Standard Band Plan",
        help_text="Select a standard band plan to auto-populate frequency range",
    )

    class Meta:
        model = WirelessChassis
        fields = CHASSIS_ADMIN_WRITE_FIELDS

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

        scope_user = type(self).scope_user
        if scope_user is not None and "location" not in self.errors:
            location = cleaned_data.get("location")
            try:
                ChassisAdminService.ensure_location_write_allowed(
                    user=scope_user,
                    location=location,
                )
                WirelessChassisPersistenceService.validate_location_quota(
                    chassis_id=self.instance.pk,
                    location=location,
                    using=self.instance._state.db,
                )
            except (PermissionDenied, OrganizationDeviceQuotaExceededError) as exc:
                self.add_error("location", str(exc))

        return cleaned_data
