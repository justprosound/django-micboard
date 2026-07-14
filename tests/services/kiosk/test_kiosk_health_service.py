"""Bounded, tenant-safe kiosk health projection contracts."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

import pytest

from micboard.services.kiosk import health_service
from micboard.services.kiosk.health_service import KioskHealthService
from tests.factories.base import UserFactory
from tests.factories.hardware import (
    ChargerFactory,
    ChargerSlotFactory,
    DisplayWallFactory,
    WallSectionFactory,
)
from tests.factories.locations import LocationFactory
from tests.factories.monitoring import MonitoringGroupFactory

pytestmark = pytest.mark.django_db


def _superuser():
    return UserFactory(is_staff=True, is_superuser=True)


def test_missing_or_inaccessible_wall_fails_closed() -> None:
    """Unknown and out-of-scope identifiers expose no health inventory."""
    assert KioskHealthService.get_wall_health(wall_id=999_999, user=_superuser()) is None

    user = UserFactory()
    wall = DisplayWallFactory()
    assert KioskHealthService.get_wall_health(wall_id=wall.pk, user=user) is None


def test_slot_checks_preserve_connection_issue_semantics() -> None:
    """Occupied identity, status, battery, and heartbeat checks remain explicit."""
    now = timezone.now()
    fresh = ChargerFactory(last_seen=now)

    empty = KioskHealthService._check_slot(
        ChargerSlotFactory(charger=fresh, occupied=False),
        now=now,
    )
    no_serial = KioskHealthService._check_slot(
        ChargerSlotFactory(charger=fresh, slot_number=2, occupied=True, device_serial=""),
        now=now,
    )
    fault = KioskHealthService._check_slot(
        ChargerSlotFactory(
            charger=fresh,
            slot_number=3,
            occupied=True,
            device_serial="faulted",
            device_status="OFFLINE",
        ),
        now=now,
    )
    low_battery = KioskHealthService._check_slot(
        ChargerSlotFactory(
            charger=fresh,
            slot_number=4,
            occupied=True,
            device_serial="low",
            battery_percent=4,
        ),
        now=now,
    )
    healthy = KioskHealthService._check_slot(
        ChargerSlotFactory(
            charger=fresh,
            slot_number=5,
            occupied=True,
            device_serial="healthy",
        ),
        now=now,
    )

    assert empty.issues == ["Slot not marked as occupied"]
    assert no_serial.issues == ["No device serial number"]
    assert fault.issues == ["Device status is OFFLINE"]
    assert low_battery.connected is True
    assert low_battery.is_valid is False
    assert low_battery.issues == ["Battery critically low: 4%"]
    assert healthy.connected is True
    assert healthy.is_valid is True


def test_slot_checks_reject_missing_and_stale_heartbeats() -> None:
    """A docked device is disconnected when its charger heartbeat is absent or stale."""
    now = timezone.now()
    unseen = ChargerFactory(last_seen=None)
    stale = ChargerFactory(last_seen=now - timedelta(seconds=121))

    unseen_result = KioskHealthService._check_slot(
        ChargerSlotFactory(charger=unseen, occupied=True, device_serial="unseen"),
        now=now,
    )
    stale_result = KioskHealthService._check_slot(
        ChargerSlotFactory(charger=stale, occupied=True, device_serial="stale"),
        now=now,
    )

    assert unseen_result.issues == ["Charger has never reported a heartbeat"]
    assert stale_result.connected is False
    assert stale_result.issues == ["Charger not seen for 121s (timeout: 120s)"]


def test_wall_health_classifies_chargers_and_deduplicates_shared_inventory() -> None:
    """One charger appears once even when multiple visible sections reference it."""
    user = _superuser()
    wall = DisplayWallFactory()
    first_section = WallSectionFactory(wall=wall, display_order=1)
    second_section = WallSectionFactory(wall=wall, display_order=2)
    offline = ChargerFactory(location=wall.location, last_seen=None, ip=None)
    degraded = ChargerFactory(location=wall.location, last_seen=timezone.now())
    idle = ChargerFactory(location=wall.location, last_seen=timezone.now())
    healthy = ChargerFactory(location=wall.location, last_seen=timezone.now(), slot_count=2)
    first_section.chargers.add(offline, degraded, idle, healthy)
    second_section.chargers.add(healthy)
    ChargerSlotFactory(charger=offline, occupied=True, device_serial="offline")
    ChargerSlotFactory(
        charger=degraded,
        occupied=True,
        device_serial="degraded",
        battery_percent=1,
    )
    ChargerSlotFactory(charger=idle, occupied=False)
    ChargerSlotFactory(charger=healthy, occupied=True, device_serial="healthy")
    ChargerSlotFactory(charger=healthy, slot_number=2, occupied=False)

    result = KioskHealthService.get_wall_health(wall_id=wall.pk, user=user)

    assert result is not None
    by_id = {entry.charger.id: entry for entry in result.chargers}
    assert len(result.chargers) == 4
    assert by_id[offline.pk].health == "offline"
    assert by_id[offline.pk].charger.ip is None
    assert by_id[degraded.pk].health == "degraded"
    assert by_id[idle.pk].health == "idle"
    assert by_id[healthy.pk].health == "healthy"
    assert by_id[healthy.pk].occupied_slots == 1
    assert by_id[healthy.pk].connected_slots == 1
    assert by_id[healthy.pk].total_slots == 2


def test_wall_health_bounds_each_tenant_scoped_dimension(
    django_assert_num_queries,
    monkeypatch,
) -> None:
    """Sentinel rows report overflow without allowing inaccessible rows to consume limits."""
    monkeypatch.setattr(health_service, "MAX_KIOSK_SECTIONS", 2)
    monkeypatch.setattr(health_service, "MAX_KIOSK_CHARGERS_PER_SECTION", 2)
    monkeypatch.setattr(health_service, "MAX_KIOSK_SLOTS_PER_CHARGER", 2)
    user = UserFactory()
    wall = DisplayWallFactory()
    group = MonitoringGroupFactory()
    group.users.add(user)
    group.locations.add(wall.location)
    sections = [WallSectionFactory(wall=wall, display_order=index) for index in range(3)]

    foreign_location = LocationFactory()
    sections[0].chargers.add(
        ChargerFactory(location=foreign_location),
        ChargerFactory(location=foreign_location),
    )
    visible = [ChargerFactory(location=wall.location, last_seen=timezone.now()) for _ in range(3)]
    sections[0].chargers.add(*visible)
    for charger in visible:
        for slot_number in (3, 1, 2):
            ChargerSlotFactory(
                charger=charger,
                slot_number=slot_number,
                occupied=True,
                device_serial=f"{charger.pk}-{slot_number}",
            )

    with django_assert_num_queries(4):
        result = KioskHealthService.get_wall_health(wall_id=wall.pk, user=user)

    assert result is not None
    assert result.sections_truncated is True
    assert result.chargers_truncated is True
    assert result.slots_truncated is True
    assert result.section_limit == 2
    assert result.charger_limit == 4
    assert result.slot_limit == 2
    assert [entry.charger.id for entry in result.chargers] == [
        visible[0].pk,
        visible[1].pk,
    ]
    assert all(len(entry.slots) == 2 for entry in result.chargers)
