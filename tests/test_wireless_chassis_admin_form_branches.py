"""Focused band-plan presentation and mapping coverage for the chassis admin form."""

from __future__ import annotations

from unittest.mock import patch

from micboard.admin.forms import WirelessChassisAdminForm
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis


def test_wireless_chassis_admin_form_populates_and_disables_band_plan_selector() -> None:
    manufacturer = Manufacturer(pk=1, code="SHURE")
    chassis = WirelessChassis(
        manufacturer=manufacturer,
        band_plan_name="G50",
    )
    with patch(
        "micboard.admin.forms.get_available_band_plans",
        return_value=[("g50", "G50"), ("h4_us", "H4-US")],
    ) as get_plans:
        form = WirelessChassisAdminForm(instance=chassis)
    get_plans.assert_called_once_with(manufacturer="shure")
    assert form.fields["band_plan_selector"].initial == "g50"
    assert len(list(form.fields["band_plan_selector"].choices)) == 3

    disabled = WirelessChassisAdminForm(instance=WirelessChassis())
    assert disabled.fields["band_plan_selector"].disabled is True
    assert "manufacturer first" in next(iter(disabled.fields["band_plan_selector"].choices))[1]

    with patch(
        "micboard.admin.forms.get_available_band_plans",
        return_value=[("g50", "G50")],
    ):
        no_current = WirelessChassisAdminForm(
            instance=WirelessChassis(manufacturer=manufacturer, band_plan_name="")
        )
        unmatched = WirelessChassisAdminForm(
            instance=WirelessChassis(manufacturer=manufacturer, band_plan_name="Custom")
        )
    assert no_current.fields["band_plan_selector"].initial is None
    assert unmatched.fields["band_plan_selector"].initial is None


def test_wireless_chassis_admin_form_clean_maps_selected_plan_and_handles_none() -> None:
    form = WirelessChassisAdminForm(instance=WirelessChassis())
    form.fields["band_plan_selector"].choices = [("g50", "G50")]
    with patch("django.forms.models.BaseModelForm.clean", return_value=None):
        assert form.clean() == {}
    with patch(
        "django.forms.models.BaseModelForm.clean", return_value={"band_plan_selector": "g50"}
    ):
        assert form.clean()["band_plan_name"] == "G50"
    with patch(
        "django.forms.models.BaseModelForm.clean", return_value={"band_plan_selector": "missing"}
    ):
        assert "band_plan_name" not in form.clean()
