"""Wireless-unit health, assignment, and lifecycle service contracts."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.utils import timezone

import pytest

from micboard.services.hardware.wireless_unit_service import (
    finalize_unit_save,
    get_assigned_rf_channel,
    get_battery_health,
    get_battery_health_display_icon,
    get_regulatory_status,
    get_signal_quality,
    is_active_at_time,
    prepare_unit_for_save,
)
from tests.factories.hardware import WirelessUnitFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("battery", "api_health", "expected"),
    [
        (255, "unknown", "unknown"),
        (200, "excellent", "excellent"),
        (200, "unknown", "good"),
        (128, "", "fair"),
        (100, "unknown", "fair"),
        (50, "unknown", "poor"),
        (20, "unknown", "critical"),
    ],
)
def test_battery_health_prefers_api_and_computes_fallback(
    battery: int,
    api_health: str,
    expected: str,
) -> None:
    """Manufacturer health wins while raw battery bytes provide stable fallback bands."""
    unit = SimpleNamespace(battery=battery, battery_health=api_health)
    assert get_battery_health(unit) == expected


@pytest.mark.parametrize(
    ("health", "expected"),
    [
        ("excellent", "🔋✨"),
        ("good", "🔋"),
        ("fair", "🔋⚠️"),
        ("poor", "🪫"),
        ("critical", "🪫❗"),
        ("unknown", "❓"),
        ("vendor-state", "❓"),
    ],
)
def test_battery_health_icon_has_safe_fallback(
    health: str,
    expected: str,
) -> None:
    """Every standard and vendor-specific battery state has a display-safe icon."""
    unit = SimpleNamespace(battery=255, battery_health=health)
    assert get_battery_health_display_icon(unit) == expected


def test_active_at_time_requires_active_recent_timestamp() -> None:
    """Activity combines lifecycle state with a five-minute freshness window."""
    now = timezone.now()
    assert (
        is_active_at_time(
            SimpleNamespace(status="offline", last_seen=now, updated_at=now),
            now,
        )
        is False
    )
    assert (
        is_active_at_time(
            SimpleNamespace(status="online", last_seen=None, updated_at=None),
            now,
        )
        is False
    )
    assert (
        is_active_at_time(
            SimpleNamespace(status="online", last_seen=now - timedelta(minutes=4), updated_at=None),
            now,
        )
        is True
    )
    assert (
        is_active_at_time(
            SimpleNamespace(
                status="degraded",
                last_seen=None,
                updated_at=now - timedelta(minutes=5),
            ),
            now,
        )
        is False
    )
    assert (
        is_active_at_time(
            SimpleNamespace(status="provisioning", last_seen=timezone.now(), updated_at=None)
        )
        is True
    )


@pytest.mark.parametrize(
    ("quality", "expected"),
    [(255, "unknown"), (201, "excellent"), (151, "good"), (101, "fair"), (100, "poor")],
)
def test_signal_quality_thresholds(quality: int, expected: str) -> None:
    """Signal bytes map onto the documented qualitative thresholds."""
    assert get_signal_quality(SimpleNamespace(quality=quality)) == expected


def test_assigned_channel_prefers_active_receive_then_direct_resource() -> None:
    """Receive activity wins, but an empty reverse relation falls back to explicit assignment."""
    active = object()
    direct = object()
    reverse = Mock()
    reverse.first.return_value = active
    unit = SimpleNamespace(active_on_receive_channels=reverse, assigned_resource=direct)
    assert get_assigned_rf_channel(unit) is active

    reverse.first.return_value = None
    assert get_assigned_rf_channel(unit) is direct
    assert get_assigned_rf_channel(SimpleNamespace(assigned_resource=direct)) is direct
    assert get_assigned_rf_channel(SimpleNamespace(assigned_resource=None)) is None
    assert get_assigned_rf_channel(SimpleNamespace()) is None

    assert (
        get_assigned_rf_channel(
            SimpleNamespace(
                _admin_active_receive_channels=[active],
                assigned_resource=direct,
            )
        )
        is active
    )
    assert (
        get_assigned_rf_channel(
            SimpleNamespace(
                _admin_active_receive_channels=[],
                assigned_resource=direct,
            )
        )
        is direct
    )


def test_regulatory_status_delegates_to_assigned_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unit regulatory context identifies the RF channel that supplied it."""
    channel = SimpleNamespace(channel_number=4)
    monkeypatch.setattr(
        "micboard.services.hardware.wireless_unit_service.get_assigned_rf_channel",
        Mock(return_value=channel),
    )
    channel_status = {"has_coverage": True, "message": "covered"}
    monkeypatch.setattr(
        "micboard.services.hardware.rf_channel_service.get_regulatory_status",
        Mock(return_value=channel_status),
    )

    result = get_regulatory_status(SimpleNamespace())

    assert result["source"] == "rf_channel"
    assert result["message"] == "Via RFChannel 4: covered"


def test_prepare_new_unit_has_empty_lifecycle_context() -> None:
    """New units have no prior state or battery to compare."""
    unit = WirelessUnitFactory.build()
    assert prepare_unit_for_save(unit) == {
        "old_status": None,
        "old_battery": None,
        "status_changed": False,
        "battery_changed": False,
        "update_fields": set(),
    }


def test_prepare_existing_unit_tracks_battery_and_state_changes() -> None:
    """Valid operational transitions derive last-seen persistence and prior values."""
    unit = WirelessUnitFactory(status="provisioning", battery=100, last_seen=None)
    unit.status = "online"
    unit.battery = 80

    context = prepare_unit_for_save(unit)

    assert context["old_status"] == "provisioning"
    assert context["old_battery"] == 100
    assert context["status_changed"] is True
    assert context["battery_changed"] is True
    assert context["update_fields"] == {"last_seen"}
    assert unit.last_seen is not None


def test_prepare_existing_unit_handles_noop_nonoperational_and_invalid_states() -> None:
    """No-op and valid nonoperational changes avoid timestamps; invalid changes fail."""
    unchanged = WirelessUnitFactory(status="online", battery=100)
    assert prepare_unit_for_save(unchanged)["status_changed"] is False

    retiring = WirelessUnitFactory(status="maintenance")
    retiring.status = "retired"
    context = prepare_unit_for_save(retiring)
    assert context["status_changed"] is True
    assert context["update_fields"] == set()

    invalid = WirelessUnitFactory(status="online")
    invalid.status = "retired"
    with pytest.raises(ValueError, match="online → retired"):
        prepare_unit_for_save(invalid)

    type(invalid).objects.filter(pk=invalid.pk).update(status="terminal")
    invalid.status = "online"
    with pytest.raises(ValueError, match="Allowed: none"):
        prepare_unit_for_save(invalid)


def test_finalize_unit_logs_status_change() -> None:
    """Persisted lifecycle transitions create one structured audit event."""
    unit = SimpleNamespace(status="online", battery=255)
    with patch("micboard.services.maintenance.audit.AuditService.log_activity") as log:
        finalize_unit_save(
            unit,
            {
                "status_changed": True,
                "old_status": "provisioning",
                "battery_changed": False,
            },
        )

    log.assert_called_once()
    assert log.call_args.kwargs["operation"] == "status_change"


def test_finalize_unit_ignores_nonactionable_battery_changes() -> None:
    """Unknown, initial, improving, and non-threshold battery changes do not alert."""
    cases = [
        (SimpleNamespace(battery=100), {"battery_changed": False, "old_battery": 120}),
        (SimpleNamespace(battery=255), {"battery_changed": True, "old_battery": 120}),
        (SimpleNamespace(battery=100), {"battery_changed": True, "old_battery": None}),
        (SimpleNamespace(battery=100), {"battery_changed": True, "old_battery": 255}),
        (SimpleNamespace(battery=120), {"battery_changed": True, "old_battery": 100}),
        (SimpleNamespace(battery=80), {"battery_changed": True, "old_battery": 100}),
    ]
    with patch("micboard.services.maintenance.audit.AuditService.log_activity") as log:
        for unit, context in cases:
            finalize_unit_save(unit, {"status_changed": False, **context})

    log.assert_not_called()


@pytest.mark.parametrize(
    ("old_battery", "new_battery", "expected_mode"),
    [(100, 60, "normal"), (60, 30, "passive")],
)
def test_finalize_unit_logs_downward_threshold_crossing(
    old_battery: int,
    new_battery: int,
    expected_mode: str,
) -> None:
    """Battery audits fire once when crossing 25% or 15% downward."""
    unit = SimpleNamespace(battery=new_battery)
    with patch("micboard.services.maintenance.audit.AuditService.log_activity") as log:
        finalize_unit_save(
            unit,
            {
                "status_changed": False,
                "battery_changed": True,
                "old_battery": old_battery,
            },
        )

    log.assert_called_once()
    assert log.call_args.kwargs["operation"] == "battery_warning"
    assert log.call_args.kwargs["log_mode"] == expected_mode
