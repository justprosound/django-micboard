"""Coverage for RF channel, wireless-unit, and charger admin behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

import pytest

from micboard.admin import (
    channels,
    chargers,
)
from micboard.admin.mixins import MicboardModelAdmin
from micboard.models.hardware.charger import ChargerSlot
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.rf_coordination.rf_channel import RFChannel

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
        assert model_admin.get_queryset(_request()) is queryset.annotate.return_value
    queryset.annotate.assert_called_once_with(_has_specific_band="exists")
    unit = SimpleNamespace(name="Mic", slot=2)
    assert "Mic" in model_admin.active_unit(SimpleNamespace(active_wireless_unit=unit))
    assert model_admin.active_unit(SimpleNamespace(active_wireless_unit=None)) == "✗ None"


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
            None,
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
            {"needs_update": True, "has_coverage": False, "operating_frequency_mhz": 500},
            "Missing coverage",
        ),
        (
            SimpleNamespace(
                chassis=SimpleNamespace(
                    location=SimpleNamespace(building=SimpleNamespace(regulatory_domain=object()))
                ),
                frequency=500,
            ),
            {"needs_update": False, "has_coverage": True, "operating_frequency_mhz": 500},
            "OK",
        ),
        (
            SimpleNamespace(
                chassis=SimpleNamespace(
                    location=SimpleNamespace(building=SimpleNamespace(regulatory_domain=object()))
                ),
                frequency=500,
            ),
            {"needs_update": False, "has_coverage": False, "operating_frequency_mhz": 500},
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
    with patch.object(channels, "get_regulatory_status", return_value=status):
        assert expected in model_admin.regulatory_status_display(object())


def test_charger_slot_display_helpers() -> None:
    model_admin = _admin(chargers.ChargerSlotAdmin, ChargerSlot)
    assert model_admin.device_info(SimpleNamespace(device_model="ULX", device_serial="123")) == (
        "ULX (123)"
    )
    assert model_admin.device_info(SimpleNamespace(device_model="", device_serial="123")) == "123"
    assert model_admin.device_info(SimpleNamespace(device_model="", device_serial="")) == "-"
    assert model_admin.is_occupied(SimpleNamespace(occupied=True)) is True
