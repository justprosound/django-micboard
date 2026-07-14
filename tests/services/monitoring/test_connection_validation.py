"""Charger heartbeat and slot connection validation contracts."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

import pytest

from micboard.services.monitoring.connection_validation import ConnectionValidationService
from tests.factories.hardware import ChargerFactory, ChargerSlotFactory
from tests.factories.locations import LocationFactory

pytestmark = pytest.mark.django_db


def _fresh_charger(**overrides):
    return ChargerFactory(last_seen=timezone.now(), **overrides)


def test_empty_slot_is_disconnected() -> None:
    """An unoccupied slot reports its explicit inventory state."""
    result = ConnectionValidationService.check_slot_connection(ChargerSlotFactory(occupied=False))

    assert result["connected"] is False
    assert result["is_valid"] is False
    assert result["issues"] == ["Slot not marked as occupied"]


def test_occupied_slot_requires_device_serial() -> None:
    """Occupied slots without device identity cannot be trusted."""
    result = ConnectionValidationService.check_slot_connection(
        ChargerSlotFactory(
            charger=_fresh_charger(),
            occupied=True,
            device_serial="",
        )
    )

    assert result["issues"] == ["No device serial number"]


@pytest.mark.parametrize("status", ["error", "OFFLINE", "fault"])
def test_error_device_states_are_disconnected(status: str) -> None:
    """Known terminal device states fail slot validation case-insensitively."""
    result = ConnectionValidationService.check_slot_connection(
        ChargerSlotFactory(
            charger=_fresh_charger(),
            occupied=True,
            device_serial="unit-1",
            device_status=status,
        )
    )

    assert result["connected"] is False
    assert result["issues"] == [f"Device status is {status}"]


def test_critical_battery_remains_connected_but_invalid() -> None:
    """A live critically-low device is connected while still requiring attention."""
    result = ConnectionValidationService.check_slot_connection(
        ChargerSlotFactory(
            charger=_fresh_charger(),
            occupied=True,
            device_serial="unit-2",
            device_status="charging",
            battery_percent=4,
        )
    )

    assert result["connected"] is True
    assert result["is_valid"] is False
    assert result["issues"] == ["Battery critically low: 4%"]


def test_occupied_slot_requires_charger_heartbeat() -> None:
    """A device cannot be considered connected through a never-seen charger."""
    result = ConnectionValidationService.check_slot_connection(
        ChargerSlotFactory(
            charger=ChargerFactory(last_seen=None),
            occupied=True,
            device_serial="unit-3",
        )
    )

    assert result["connected"] is False
    assert result["issues"] == ["Charger has never reported a heartbeat"]


def test_stale_charger_disconnects_slot() -> None:
    """Heartbeat age is enforced at the documented timeout boundary."""
    charger = ChargerFactory(last_seen=timezone.now() - timedelta(seconds=121))
    result = ConnectionValidationService.check_slot_connection(
        ChargerSlotFactory(charger=charger, occupied=True, device_serial="unit-4")
    )

    assert result["connected"] is False
    assert "Charger not seen for" in result["issues"][0]
    assert "timeout: 120s" in result["issues"][0]


def test_recent_healthy_slot_is_valid() -> None:
    """A recently seen identified device with no issues is valid and connected."""
    result = ConnectionValidationService.check_slot_connection(
        ChargerSlotFactory(
            charger=_fresh_charger(),
            occupied=True,
            device_serial="unit-5",
            device_status="",
            battery_percent=None,
        )
    )

    assert result["connected"] is True
    assert result["is_valid"] is True
    assert result["issues"] == []


def test_missing_charger_health_is_unknown() -> None:
    """A deleted or unknown charger ID has a stable not-found payload."""
    assert ConnectionValidationService.check_charger_health(999_999) == {
        "charger_id": 999_999,
        "found": False,
        "health": "unknown",
    }


def test_charger_health_classifies_offline_degraded_idle_and_healthy() -> None:
    """Heartbeat, issue, occupancy, and connection counts drive charger health."""
    offline = ChargerFactory(last_seen=None, ip=None)
    ChargerSlotFactory(charger=offline, occupied=True, device_serial="offline-unit")

    degraded = _fresh_charger()
    ChargerSlotFactory(
        charger=degraded,
        occupied=True,
        device_serial="low-battery",
        battery_percent=1,
    )

    idle = _fresh_charger()
    ChargerSlotFactory(charger=idle, occupied=False)

    healthy = _fresh_charger(slot_count=2)
    ChargerSlotFactory(
        charger=healthy,
        occupied=True,
        device_serial="healthy-unit",
    )
    ChargerSlotFactory(charger=healthy, slot_number=2, occupied=False)

    offline_result = ConnectionValidationService.check_charger_health(offline.id)
    degraded_result = ConnectionValidationService.check_charger_health(degraded.id)
    idle_result = ConnectionValidationService.check_charger_health(idle.id)
    healthy_result = ConnectionValidationService.check_charger_health(healthy.id)

    assert offline_result["health"] == "offline"
    assert offline_result["charger"]["ip"] is None
    assert degraded_result["health"] == "degraded"
    assert degraded_result["issue_count"] == 1
    assert idle_result["health"] == "idle"
    assert healthy_result["health"] == "healthy"
    assert healthy_result["occupied_slots"] == 1
    assert healthy_result["connected_slots"] == 1
    assert healthy_result["total_slots"] == 2
    assert healthy_result["charger"]["ip"] == str(healthy.ip)


def test_location_health_is_query_bounded_and_uses_worst_charger(
    django_assert_num_queries,
) -> None:
    """Location aggregation prefetches slots once and selects the worst health."""
    location = LocationFactory()
    healthy = _fresh_charger(location=location)
    ChargerSlotFactory(
        charger=healthy,
        occupied=True,
        device_serial="healthy-unit",
    )
    offline = ChargerFactory(location=location, last_seen=None)
    ChargerSlotFactory(charger=offline, occupied=False)
    ChargerFactory(location=location, is_active=False)

    with django_assert_num_queries(2):
        result = ConnectionValidationService.check_location_charger_health(location.id)

    assert result["charger_count"] == 2
    assert result["overall_health"] == "offline"
    assert len(result["chargers"]) == 2


def test_empty_location_health_is_unknown() -> None:
    """Locations without active chargers remain explicitly unknown."""
    location = LocationFactory()

    assert ConnectionValidationService.check_location_charger_health(location.id) == {
        "location_id": location.id,
        "charger_count": 0,
        "overall_health": "unknown",
        "chargers": [],
    }


def test_validate_device_on_slot_checks_connection_and_expected_serial() -> None:
    """Optional expected identity is enforced only after connection validation."""
    invalid = ChargerSlotFactory(occupied=False)
    valid = ChargerSlotFactory(
        charger=_fresh_charger(),
        occupied=True,
        device_serial="unit-6",
    )

    assert ConnectionValidationService.validate_device_on_slot(invalid) is False
    assert ConnectionValidationService.validate_device_on_slot(valid) is True
    assert ConnectionValidationService.validate_device_on_slot(valid, "unit-6") is True
    assert ConnectionValidationService.validate_device_on_slot(valid, "other") is False


def test_unhealthy_slot_queries_handle_missing_and_filter_healthy_slots() -> None:
    """Per-charger unhealthy results contain issue-bearing slots only."""
    assert ConnectionValidationService.get_unhealthy_slots(999_999) == []

    charger = _fresh_charger(slot_count=2)
    ChargerSlotFactory(
        charger=charger,
        occupied=True,
        device_serial="healthy-unit",
    )
    unhealthy = ChargerSlotFactory(charger=charger, slot_number=2, occupied=False)

    result = ConnectionValidationService.get_unhealthy_slots(charger.id)

    assert [item["slot_id"] for item in result] == [unhealthy.id]


def test_all_unhealthy_slots_prefetches_active_location_inventory(
    django_assert_num_queries,
) -> None:
    """Cross-charger issue reporting avoids one query pair per charger."""
    location = LocationFactory()
    first = _fresh_charger(location=location, name="First")
    first_slot = ChargerSlotFactory(charger=first, occupied=False)
    second = _fresh_charger(location=location, name="Second")
    second_slot = ChargerSlotFactory(charger=second, occupied=False)
    inactive = _fresh_charger(location=location, name="Inactive", is_active=False)
    ChargerSlotFactory(charger=inactive, occupied=False)

    with django_assert_num_queries(2):
        result = ConnectionValidationService.get_all_unhealthy_slots(location.id)

    assert {(item["slot_id"], item["charger_name"]) for item in result} == {
        (first_slot.id, "First"),
        (second_slot.id, "Second"),
    }
