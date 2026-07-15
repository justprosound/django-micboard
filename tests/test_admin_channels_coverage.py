"""Coverage for RF channel, wireless-unit, and charger admin behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.db import connection
from django.forms.models import model_to_dict
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

import pytest

from micboard.admin import (
    channels,
    chargers,
)
from micboard.admin.channel_forms import RFChannelAdminForm, WirelessUnitAdminForm
from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.hardware.charger import ChargerSlot
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.rf_coordination.rf_channel import RFChannel
from tests.factories.hardware import WirelessChassisFactory, WirelessUnitFactory
from tests.factories.locations import BuildingFactory, LocationFactory
from tests.factories.rf_coordination import RegulatoryDomainFactory, RFChannelFactory

NOW = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def _request() -> Any:
    request = RequestFactory().get("/admin/")
    request.user = SimpleNamespace(pk=4, is_authenticated=True, is_superuser=True)
    return request


def _admin(admin_class: type, model: type) -> Any:
    return admin_class(model, AdminSite())


def test_rf_channel_queryset_annotation_and_active_unit_display() -> None:
    model_admin = _admin(channels.RFChannelAdmin, RFChannel)
    queryset = MagicMock()
    bands = MagicMock()
    with (
        patch.object(MicboardModelAdmin, "get_queryset", return_value=queryset),
        patch.object(channels.FrequencyBand.objects, "filter", return_value=bands),
        patch.object(channels, "Exists", return_value="exists"),
    ):
        result = model_admin.get_queryset(_request())
    assert result is queryset.annotate.return_value.annotate.return_value
    queryset.annotate.assert_called_once_with(_has_specific_band="exists")
    unit = SimpleNamespace(name="Mic", slot=2)
    assert "Mic" in model_admin.active_unit(SimpleNamespace(active_wireless_unit=unit))
    assert model_admin.active_unit(SimpleNamespace(active_wireless_unit=None)) == "✗ None"


@pytest.mark.django_db
def test_rf_channel_admin_form_rejects_units_from_another_chassis() -> None:
    channel = RFChannelFactory()
    foreign_unit = WirelessUnitFactory(
        base_chassis=WirelessChassisFactory(max_channels=0),
    )
    data = model_to_dict(channel)
    data["active_wireless_unit"] = foreign_unit.pk

    form = RFChannelAdminForm(data=data, instance=channel)

    assert not form.is_valid()
    assert "selected chassis" in form.errors["active_wireless_unit"][0]


@pytest.mark.django_db
def test_wireless_unit_admin_form_rejects_resources_from_another_chassis() -> None:
    unit = WirelessUnitFactory(base_chassis=WirelessChassisFactory(max_channels=0))
    foreign_channel = RFChannelFactory()
    data = model_to_dict(unit)
    data["assigned_resource"] = foreign_channel.pk

    form = WirelessUnitAdminForm(data=data, instance=unit)

    assert not form.is_valid()
    assert "base chassis" in form.errors["assigned_resource"][0]


@pytest.mark.django_db
def test_wireless_unit_regulatory_columns_have_constant_query_count() -> None:
    user = get_user_model().objects.create_superuser(username="channel-query-admin")
    request = RequestFactory().get("/admin/micboard/wirelessunit/")
    request.user = user
    model_admin = _admin(channels.WirelessUnitAdmin, WirelessUnit)
    RegulatoryDomainFactory(country_code="US")
    building = BuildingFactory(country="US", regulatory_domain=None)
    location = LocationFactory(building=building)

    def add_unit(index: int) -> None:
        chassis = WirelessChassisFactory(
            location=location,
            max_channels=0,
            wmas_capable=True,
        )
        channel = RFChannelFactory(
            chassis=chassis,
            channel_number=index,
            frequency=500.0,
            resource_state="active",
        )
        WirelessUnitFactory(
            base_chassis=chassis,
            assigned_resource=channel,
            slot=index,
        )

    def render_statuses() -> int:
        queryset = model_admin.get_queryset(request).select_related(
            *model_admin.list_select_related
        )
        with CaptureQueriesContext(connection) as query_context:
            [model_admin.regulatory_status_display(unit) for unit in queryset]
        return len(query_context)

    add_unit(1)
    small_query_count = render_statuses()
    for index in range(2, 6):
        add_unit(index)
    large_query_count = render_statuses()

    assert large_query_count == small_query_count
    assert large_query_count <= 2


@pytest.mark.parametrize(
    ("obj", "service_status", "expected"),
    [
        (SimpleNamespace(chassis=None, frequency=500), None, "—"),
        (
            SimpleNamespace(
                chassis=SimpleNamespace(
                    location=SimpleNamespace(building=SimpleNamespace(regulatory_domain=None))
                ),
                frequency=500,
            ),
            {
                "regulatory_domain": None,
                "needs_update": False,
                "has_coverage": False,
                "operating_frequency_mhz": 500,
            },
            "No regulatory domain",
        ),
        (
            SimpleNamespace(
                chassis=SimpleNamespace(
                    location=SimpleNamespace(building=SimpleNamespace(regulatory_domain=object()))
                ),
                frequency=None,
            ),
            None,
            "No frequency",
        ),
        (
            SimpleNamespace(
                chassis=SimpleNamespace(
                    location=SimpleNamespace(building=SimpleNamespace(regulatory_domain=object()))
                ),
                frequency=500,
            ),
            {
                "regulatory_domain": "FCC",
                "needs_update": True,
                "has_coverage": False,
                "operating_frequency_mhz": 500,
            },
            "Missing coverage",
        ),
        (
            SimpleNamespace(
                chassis=SimpleNamespace(
                    location=SimpleNamespace(building=SimpleNamespace(regulatory_domain=object()))
                ),
                frequency=500,
            ),
            {
                "regulatory_domain": "FCC",
                "needs_update": False,
                "has_coverage": True,
                "operating_frequency_mhz": 500,
            },
            "OK",
        ),
        (
            SimpleNamespace(
                chassis=SimpleNamespace(
                    location=SimpleNamespace(building=SimpleNamespace(regulatory_domain=object()))
                ),
                frequency=500,
            ),
            {
                "regulatory_domain": "FCC",
                "needs_update": False,
                "has_coverage": False,
                "operating_frequency_mhz": 500,
            },
            "—",
        ),
    ],
)
def test_rf_channel_regulatory_display_paths(
    obj: Any, service_status: dict[str, Any] | None, expected: str
) -> None:
    model_admin = _admin(channels.RFChannelAdmin, RFChannel)
    with patch.object(
        channels,
        "get_rf_channel_regulatory_status",
        return_value=service_status,
    ):
        assert expected in model_admin.regulatory_status_optimized(obj)


@pytest.mark.parametrize(
    ("percentage", "expected"),
    [(None, "Unknown"), (75, "●●●●●"), (40, "●●●○○"), (20, "●●○○○"), (5, "●○○○○")],
)
def test_wireless_unit_battery_indicator_ranges(percentage: int | None, expected: str) -> None:
    model_admin = _admin(channels.WirelessUnitAdmin, WirelessUnit)
    with patch.object(channels, "get_battery_percentage", return_value=percentage):
        assert expected in model_admin.battery_indicator(object())
        assert model_admin.battery_percentage(object()) == percentage


def test_wireless_unit_battery_health_and_detail_displays() -> None:
    model_admin = _admin(channels.WirelessUnitAdmin, WirelessUnit)
    unit = SimpleNamespace(
        battery_health="good",
        battery_cycles=12,
        battery_temperature_c=32,
        battery_runtime="2h",
    )
    with (
        patch.object(channels, "get_battery_health", return_value="good"),
        patch.object(channels, "get_battery_health_display_icon", return_value="✓"),
        patch.object(channels, "get_battery_percentage", return_value=88),
    ):
        assert "Good" in model_admin.battery_health_display(unit)
        assert model_admin.battery_health_detail_display(unit) == (
            "Health: good | 88% | 12 cycles | 32°C | Runtime: 2h"
        )
    empty = SimpleNamespace(
        battery_health="",
        battery_cycles=0,
        battery_temperature_c=None,
        battery_runtime="",
    )
    with patch.object(channels, "get_battery_percentage", return_value=None):
        assert model_admin.battery_health_detail_display(empty) == "—"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ({"source": "no_channel"}, "No RF channel"),
        ({"source": "channel", "operating_frequency_mhz": None}, "No frequency"),
        (
            {
                "source": "channel",
                "operating_frequency_mhz": 500,
                "needs_update": True,
                "has_coverage": False,
            },
            "Missing coverage",
        ),
        (
            {
                "source": "channel",
                "operating_frequency_mhz": 500,
                "needs_update": False,
                "has_coverage": True,
            },
            "OK",
        ),
        (
            {
                "source": "channel",
                "operating_frequency_mhz": 500,
                "needs_update": False,
                "has_coverage": False,
            },
            "—",
        ),
    ],
)
def test_wireless_unit_regulatory_display_paths(status: dict[str, Any], expected: str) -> None:
    model_admin = _admin(channels.WirelessUnitAdmin, WirelessUnit)
    with patch.object(channels, "get_regulatory_status_for_domain", return_value=status):
        assert expected in model_admin.regulatory_status_display(object())


def test_charger_slot_display_helpers() -> None:
    model_admin = _admin(chargers.ChargerSlotAdmin, ChargerSlot)
    assert model_admin.device_info(SimpleNamespace(device_model="ULX", device_serial="123")) == (
        "ULX (123)"
    )
    assert model_admin.device_info(SimpleNamespace(device_model="", device_serial="123")) == "123"
    assert model_admin.device_info(SimpleNamespace(device_model="", device_serial="")) == "-"
    assert model_admin.is_occupied(SimpleNamespace(occupied=True)) is True
