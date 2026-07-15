"""Validation forms for dashboard preferences."""

from django import forms

from micboard.services.core.user_profile import (
    MAX_DISPLAY_WIDTH_PX,
    MIN_DISPLAY_WIDTH_PX,
)


class DisplayWidthForm(forms.Form):
    """Validate the physical width used to scale the charger dashboard."""

    display_width_px = forms.IntegerField(
        min_value=MIN_DISPLAY_WIDTH_PX,
        max_value=MAX_DISPLAY_WIDTH_PX,
        widget=forms.NumberInput(
            attrs={
                "aria-label": "Display width in pixels",
                "class": "form-control form-control-sm",
                "id": "display-width-input",
                "style": "width: 100px;",
            }
        ),
    )
