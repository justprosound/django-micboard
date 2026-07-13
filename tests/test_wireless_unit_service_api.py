"""Regression coverage for the canonical wireless-unit service API."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.services.hardware.wireless_unit_service import (
    get_battery_health,
    get_battery_percentage,
    get_iem_metrics,
    get_regulatory_status,
    get_signal_quality,
    get_transmitter_metrics,
    is_iem_receiver,
    is_transmitter,
)
from micboard.templatetags.micboard_tags import wireless_battery_percentage

REMOVED_MODEL_APIS = (
    "battery_percentage",
    "get_battery_health",
    "get_battery_health_display_icon",
    "is_active_at_time",
    "get_signal_quality",
    "is_transmitter",
    "get_transmitter_metrics",
    "is_iem_receiver",
    "get_iem_metrics",
    "get_assigned_rf_channel",
    "get_regulatory_status",
)


def _unit(**overrides: Any) -> WirelessUnit:
    values: dict[str, Any] = {
        "battery": 255,
        "battery_health": "unknown",
        "quality": 255,
        "device_type": "mic_transmitter",
        "audio_level": -20,
        "rf_level": -60,
        "frequency": "550.100",
        "iem_link_quality": None,
        "iem_audio_level": None,
    }
    values.update(overrides)
    return cast(WirelessUnit, SimpleNamespace(**values))


def test_wireless_unit_model_has_no_service_delegation_shims() -> None:
    """Removed model APIs must not return as compatibility wrappers."""
    for name in REMOVED_MODEL_APIS:
        assert not hasattr(WirelessUnit, name)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(255, None), (0, 0), (128, 50), (510, 100)],
)
def test_battery_percentage_is_normalized(raw: int, expected: int | None) -> None:
    unit = _unit(battery=raw)
    assert get_battery_percentage(unit) == expected
    assert wireless_battery_percentage(unit) == expected


def test_battery_health_and_signal_quality_use_normalized_values() -> None:
    unit = _unit(battery=67, quality=151)
    assert get_battery_health(unit) == "fair"
    assert get_signal_quality(unit) == "good"


def test_role_specific_metrics_fail_closed_for_other_unit_types() -> None:
    transmitter = _unit(device_type="mic_transmitter")
    iem_receiver = _unit(
        device_type="iem_receiver",
        iem_link_quality=80,
        iem_audio_level=-12,
    )

    assert is_transmitter(transmitter)
    assert not is_iem_receiver(transmitter)
    assert get_transmitter_metrics(transmitter)["quality"] == "unknown"
    assert get_iem_metrics(transmitter) == {}

    assert not is_transmitter(iem_receiver)
    assert is_iem_receiver(iem_receiver)
    assert get_transmitter_metrics(iem_receiver) == {}
    assert get_iem_metrics(iem_receiver) == {
        "iem_link_quality": 80,
        "iem_audio_level": -12,
    }


def test_regulatory_status_without_channel_is_explicit() -> None:
    unit = _unit()
    status = get_regulatory_status(unit)
    assert status["source"] == "no_channel"
    assert status["has_coverage"] is False


def test_template_filter_handles_missing_units() -> None:
    assert wireless_battery_percentage(None) is None
