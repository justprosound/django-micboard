"""Relationship-safe forms for standalone RF hardware administration."""

from typing import TYPE_CHECKING, Any

from django import forms
from django.core.exceptions import ValidationError

from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.rf_coordination.rf_channel import RFChannel

if TYPE_CHECKING:
    _RFChannelModelForm = forms.ModelForm[RFChannel]
    _WirelessUnitModelForm = forms.ModelForm[WirelessUnit]
else:
    _RFChannelModelForm = forms.ModelForm
    _WirelessUnitModelForm = forms.ModelForm


class RFChannelAdminForm(_RFChannelModelForm):
    """Reject active units paired with a different chassis."""

    class Meta:
        model = RFChannel
        exclude: tuple[str, ...] = ()

    def clean(self) -> dict[str, Any]:
        """Keep both active-unit relationships inside the selected chassis."""
        cleaned_data = super().clean() or {}
        chassis = cleaned_data.get("chassis")
        for field_name in ("active_wireless_unit", "active_iem_receiver"):
            unit = cleaned_data.get(field_name)
            if chassis is not None and unit is not None and unit.base_chassis_id != chassis.pk:
                self.add_error(
                    field_name,
                    ValidationError("The active unit must belong to the selected chassis."),
                )
        return cleaned_data


class WirelessUnitAdminForm(_WirelessUnitModelForm):
    """Reject RF resources owned by a different chassis."""

    class Meta:
        model = WirelessUnit
        exclude: tuple[str, ...] = ()

    def clean(self) -> dict[str, Any]:
        """Keep the assigned RF resource inside the unit's base chassis."""
        cleaned_data = super().clean() or {}
        chassis = cleaned_data.get("base_chassis")
        resource = cleaned_data.get("assigned_resource")
        if chassis is not None and resource is not None and resource.chassis_id != chassis.pk:
            self.add_error(
                "assigned_resource",
                ValidationError("The RF resource must belong to the unit's base chassis."),
            )
        return cleaned_data
