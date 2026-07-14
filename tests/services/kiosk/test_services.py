"""Typed DisplayWall snapshot and heartbeat contracts."""

from __future__ import annotations

from types import SimpleNamespace

from django.template.loader import render_to_string

import pytest

from micboard.services.kiosk import services as kiosk_services
from micboard.services.kiosk.services import KioskService
from tests.factories.base import UserFactory
from tests.factories.hardware import (
    ChargerFactory,
    ChargerSlotFactory,
    DisplayWallFactory,
    WallSectionFactory,
    WirelessChassisFactory,
    WirelessUnitFactory,
)
from tests.factories.locations import LocationFactory
from tests.factories.monitoring import MonitoringGroupFactory, PerformerAssignmentFactory
from tests.factories.rf_coordination import RFChannelFactory

pytestmark = pytest.mark.django_db


def _superuser():
    return UserFactory(is_staff=True, is_superuser=True)


def test_performer_serializer_keeps_optional_channel_and_photo_explicit() -> None:
    """Typed projection retains optional RF and image state."""
    slot = SimpleNamespace(slot_number=2, charger_id=3)
    performer = SimpleNamespace(id=4, name="Singer", title="Lead", photo=None)
    assignment = SimpleNamespace(performer=performer, priority="high")
    unit = SimpleNamespace(
        id=5,
        assigned_resource=None,
        device_type="mic_transmitter",
        battery=255,
        status="online",
        rf_level=20,
        audio_level=10,
    )

    without_channel = KioskService._serialize_performer(slot, unit, assignment)
    assert without_channel.channel is None
    assert without_channel.performer_photo is None

    unit.assigned_resource = SimpleNamespace(
        frequency=500.1,
        channel_number=1,
        rf_signal_strength=-70,
        audio_level=-10,
        link_direction="receive",
    )
    performer.photo = SimpleNamespace(url="/media/performer.jpg")
    with_channel = KioskService._serialize_performer(slot, unit, assignment)

    assert with_channel.channel is not None
    assert with_channel.channel.frequency == 500.1
    assert with_channel.performer_photo == "/media/performer.jpg"


def test_bulk_identity_resolution_rejects_ambiguous_serials() -> None:
    """One snapshot never guesses between duplicate hardware identities."""
    user = _superuser()
    assert KioskService._get_units_by_serial([], user=user) == {}
    unique = WirelessUnitFactory(serial_number="unique")
    first_duplicate = WirelessUnitFactory(serial_number="duplicate")
    WirelessUnitFactory(serial_number="duplicate")
    slots = [
        ChargerSlotFactory.build(device_serial=""),
        ChargerSlotFactory.build(device_serial=unique.serial_number),
        ChargerSlotFactory.build(device_serial=first_duplicate.serial_number),
    ]

    result = KioskService._get_units_by_serial(slots, user=user)

    assert result["unique"] == unique
    assert result["duplicate"] is None


def test_bulk_assignment_resolution_is_priority_deterministic() -> None:
    """Critical active assignment wins regardless of creation order."""
    user = _superuser()
    assert KioskService._get_assignments_by_unit({}, user=user) == {}
    unit = WirelessUnitFactory()
    low = PerformerAssignmentFactory(wireless_unit=unit, priority="low")
    critical = PerformerAssignmentFactory(wireless_unit=unit, priority="critical")

    result = KioskService._get_assignments_by_unit({unit.serial_number: unit}, user=user)

    assert result == {unit.id: critical}
    assert result[unit.id] != low


def test_wall_and_section_snapshots_share_one_typed_projection() -> None:
    """Full and fragment adapters observe the same performer projection."""
    user = _superuser()
    wall = DisplayWallFactory(name="Stage", kiosk_id="stage")
    section = WallSectionFactory(wall=wall, name="Main")
    charger = ChargerFactory(location=wall.location, name="Rack")
    section.chargers.add(charger)
    channel = RFChannelFactory(frequency=510.2, rf_signal_strength=-60, audio_level=-12)
    unit = WirelessUnitFactory(
        base_chassis=channel.chassis,
        manufacturer=channel.chassis.manufacturer,
        assigned_resource=channel,
        serial_number="docked-unit",
    )
    assignment = PerformerAssignmentFactory(wireless_unit=unit, priority="critical")
    ChargerSlotFactory(
        charger=charger,
        occupied=True,
        device_serial=unit.serial_number,
    )

    wall_snapshot = KioskService.get_wall_snapshot(wall.pk, user=user)
    kiosk_snapshot = KioskService.get_kiosk_snapshot("stage", user=user)
    section_snapshot = KioskService.get_section_snapshot(section.pk, user=user)

    assert wall_snapshot is not None
    assert kiosk_snapshot == wall_snapshot
    assert section_snapshot == wall_snapshot.sections[0]
    performer = section_snapshot.performers[0].performers[0]
    assert performer.performer_id == assignment.performer_id
    assert performer.channel is not None
    assert performer.channel.frequency == 510.2


def test_wall_snapshot_bounds_tenant_scoped_topology_and_renders_overflow(
    django_assert_num_queries,
    monkeypatch,
) -> None:
    """Each live wall dimension keeps a stable visible prefix and reports overflow."""
    monkeypatch.setattr(kiosk_services, "MAX_KIOSK_SECTIONS", 2)
    monkeypatch.setattr(kiosk_services, "MAX_KIOSK_CHARGERS_PER_SECTION", 2)
    monkeypatch.setattr(kiosk_services, "MAX_KIOSK_OCCUPIED_SLOTS_PER_CHARGER", 2)
    user = UserFactory()
    wall = DisplayWallFactory(name="Bounded wall")
    group = MonitoringGroupFactory()
    group.users.add(user)
    group.locations.add(wall.location)
    sections = [
        WallSectionFactory(
            wall=wall,
            name=f"Visible section {index}",
            display_order=index,
        )
        for index in range(3)
    ]

    foreign_location = LocationFactory()
    for index in range(2):
        sections[0].chargers.add(
            ChargerFactory(
                location=foreign_location,
                name=f"A foreign charger {index}",
                order=0,
            )
        )

    chassis = WirelessChassisFactory(location=wall.location)
    visible_chargers = [
        ChargerFactory(
            location=wall.location,
            name=f"Visible charger {index}",
            order=index + 10,
        )
        for index in range(3)
    ]
    sections[0].chargers.add(*visible_chargers)
    unit_slot = 0
    for charger in visible_chargers:
        for slot_number in (3, 1, 2):
            unit_slot += 1
            serial_number = f"bounded-unit-{unit_slot}"
            unit = WirelessUnitFactory(
                base_chassis=chassis,
                slot=unit_slot,
                serial_number=serial_number,
            )
            PerformerAssignmentFactory(
                wireless_unit=unit,
                monitoring_group=group,
            )
            ChargerSlotFactory(
                charger=charger,
                slot_number=slot_number,
                occupied=True,
                device_serial=serial_number,
            )

    with django_assert_num_queries(6):
        snapshot = KioskService.get_wall_snapshot(wall.pk, user=user)

    assert snapshot is not None
    assert [section.name for section in snapshot.sections] == [
        "Visible section 0",
        "Visible section 1",
    ]
    assert snapshot.sections_truncated is True
    assert snapshot.section_limit == 2
    first_section = snapshot.sections[0]
    assert [group.charger.name for group in first_section.performers] == [
        "Visible charger 0",
        "Visible charger 1",
    ]
    assert first_section.chargers_truncated is True
    assert first_section.charger_limit == 2
    assert first_section.occupied_slots_truncated is True
    assert first_section.occupied_slot_limit == 2
    assert all(len(group.performers) == 2 for group in first_section.performers)
    assert all(group.occupied_slots_truncated for group in first_section.performers)

    rendered = render_to_string("micboard/kiosk/display_content.html", {"snapshot": snapshot})
    assert "Showing the first 2 wall sections" in rendered
    assert "Showing the first 2 chargers in this section" in rendered
    assert "more than 2 occupied slots" in rendered


@pytest.mark.parametrize(
    ("configured_interval", "expected_interval"),
    [(-1, 2), (86_400, 3600)],
)
def test_snapshot_clamps_preexisting_unsafe_refresh_intervals(
    configured_interval: int,
    expected_interval: int,
) -> None:
    """Stored values predating validation cannot create unsafe browser timers."""
    user = _superuser()
    wall = DisplayWallFactory(refresh_interval_seconds=configured_interval)

    snapshot = KioskService.get_wall_snapshot(wall.pk, user=user)

    assert snapshot is not None
    assert snapshot.wall.refresh_interval_seconds == expected_interval


def test_missing_snapshots_and_heartbeat_fail_closed() -> None:
    """Unknown identifiers expose no data and receive no heartbeat write."""
    user = _superuser()
    assert KioskService.get_wall_snapshot(999_999, user=user) is None
    assert KioskService.get_kiosk_snapshot("missing", user=user) is None
    assert KioskService.get_section_snapshot(999_999, user=user) is None
    assert not KioskService.record_heartbeat("missing", user=user)


def test_heartbeat_updates_only_visible_active_kiosk() -> None:
    """Heartbeat write is localized at the same access-controlled seam."""
    user = _superuser()
    wall = DisplayWallFactory(kiosk_id="heartbeat", last_heartbeat=None)

    assert KioskService.record_heartbeat("heartbeat", user=user)

    wall.refresh_from_db()
    assert wall.last_heartbeat is not None
