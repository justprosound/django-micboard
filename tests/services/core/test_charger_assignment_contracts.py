"""Charger, performer, and display-wall assignment contracts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from micboard.services.core.charger_assignment import ChargerAssignmentService
from tests.factories.base import UserFactory
from tests.factories.hardware import (
    ChargerFactory,
    ChargerSlotFactory,
    DisplayWallFactory,
    WallSectionFactory,
    WirelessUnitFactory,
)
from tests.factories.monitoring import PerformerAssignmentFactory
from tests.factories.rf_coordination import RFChannelFactory

pytestmark = pytest.mark.django_db


def _superuser():
    return UserFactory(is_staff=True, is_superuser=True)


def test_slot_serializer_handles_optional_channel_and_photo() -> None:
    """Serialized performer data keeps optional RF and image context explicit."""
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

    without_channel = ChargerAssignmentService._serialize_performer_for_slot(
        slot,
        unit,
        assignment,
    )
    assert without_channel["channel"] is None
    assert without_channel["performer_photo"] is None

    unit.assigned_resource = SimpleNamespace(
        frequency=500.1,
        channel_number=1,
        rf_signal_strength=-70,
        audio_level=-10,
        link_direction="receive",
    )
    performer.photo = SimpleNamespace(url="/media/performer.jpg")
    with_channel = ChargerAssignmentService._serialize_performer_for_slot(
        slot,
        unit,
        assignment,
    )
    assert with_channel["channel"] == {
        "frequency": 500.1,
        "channel_number": 1,
        "rf_signal_strength": -70,
        "audio_level": -10,
        "link_direction": "receive",
    }
    assert with_channel["performer_photo"] == "/media/performer.jpg"


@pytest.mark.parametrize(
    ("occupied", "serial"),
    [(False, "unit"), (True, "")],
)
def test_slot_performer_requires_occupied_identified_device(
    occupied: bool,
    serial: str,
) -> None:
    """Empty or anonymous slots avoid inventory queries."""
    slot = ChargerSlotFactory.build(occupied=occupied, device_serial=serial)

    assert ChargerAssignmentService.get_performer_for_slot(slot, user=_superuser()) is None


def test_slot_performer_returns_active_assignment_with_channel() -> None:
    """A visible docked unit resolves its active performer and RF resource."""
    user = _superuser()
    channel = RFChannelFactory(frequency=510.2, rf_signal_strength=-60, audio_level=-12)
    unit = WirelessUnitFactory(
        base_chassis=channel.chassis,
        manufacturer=channel.chassis.manufacturer,
        assigned_resource=channel,
        serial_number="docked-unit",
    )
    assignment = PerformerAssignmentFactory(wireless_unit=unit, priority="critical")
    slot = ChargerSlotFactory(occupied=True, device_serial=unit.serial_number)

    result = ChargerAssignmentService.get_performer_for_slot(slot, user=user)

    assert result is not None
    assert result["performer_id"] == assignment.performer_id
    assert result["unit_id"] == unit.id
    assert result["channel"]["frequency"] == 510.2
    assert result["assignment_priority"] == "critical"


def test_slot_performer_handles_missing_unit_assignment_and_query_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stale slot identity, absent assignment, and ORM errors all fail closed."""
    user = _superuser()
    missing = ChargerSlotFactory(occupied=True, device_serial="missing")
    assert ChargerAssignmentService.get_performer_for_slot(missing, user=user) is None

    unit = WirelessUnitFactory(serial_number="unassigned")
    unassigned = ChargerSlotFactory(occupied=True, device_serial=unit.serial_number)
    assert ChargerAssignmentService.get_performer_for_slot(unassigned, user=user) is None

    monkeypatch.setattr(
        type(unit).objects,
        "for_user",
        Mock(side_effect=RuntimeError("database unavailable")),
    )
    assert ChargerAssignmentService.get_performer_for_slot(unassigned, user=user) is None


def test_charger_performers_handles_missing_and_filters_empty_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Charger aggregation returns only occupied slots with resolved performers."""
    user = _superuser()
    assert ChargerAssignmentService.get_charger_performers(999_999, user=user) == []

    charger = ChargerFactory(slot_count=2)
    first = ChargerSlotFactory(charger=charger, occupied=True, device_serial="first")
    ChargerSlotFactory(charger=charger, slot_number=2, occupied=True, device_serial="second")
    performer = {"performer_name": "Singer"}
    resolve = Mock(side_effect=[performer, None])
    monkeypatch.setattr(ChargerAssignmentService, "get_performer_for_slot", resolve)

    assert ChargerAssignmentService.get_charger_performers(charger.id, user=user) == [performer]
    assert resolve.call_args_list[0].args == (first,)


def test_wall_section_performers_handles_missing_and_visible_chargers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Section aggregation groups nonempty visible charger results."""
    user = _superuser()
    assert ChargerAssignmentService.get_wall_section_performers(999_999, user=user) == []

    wall = DisplayWallFactory()
    section = WallSectionFactory(wall=wall)
    first = ChargerFactory(location=wall.location, name="First")
    second = ChargerFactory(location=wall.location, name="Second")
    section.chargers.add(first, second)
    aggregate = Mock(side_effect=[[{"performer_name": "Singer"}], []])
    monkeypatch.setattr(ChargerAssignmentService, "get_charger_performers", aggregate)

    result = ChargerAssignmentService.get_wall_section_performers(section.id, user=user)

    assert result == [
        {
            "charger": {
                "id": first.id,
                "name": "First",
                "location_id": first.location_id,
            },
            "performers": [{"performer_name": "Singer"}],
        }
    ]


def test_bulk_unit_lookup_handles_empty_unique_and_ambiguous_serials() -> None:
    """Bulk identity resolution rejects ambiguous duplicate serials."""
    user = _superuser()
    assert ChargerAssignmentService._get_units_by_serial([], user=user) == {}

    unique = WirelessUnitFactory(serial_number="unique")
    first_duplicate = WirelessUnitFactory(serial_number="duplicate")
    WirelessUnitFactory(serial_number="duplicate")
    slots = [
        ChargerSlotFactory.build(device_serial=""),
        ChargerSlotFactory.build(device_serial=unique.serial_number),
        ChargerSlotFactory.build(device_serial=first_duplicate.serial_number),
    ]

    result = ChargerAssignmentService._get_units_by_serial(slots, user=user)

    assert result["unique"] == unique
    assert result["duplicate"] is None


def test_bulk_assignment_lookup_handles_empty_and_keeps_first_active_assignment() -> None:
    """Bulk assignment selection is deterministic for units with multiple performers."""
    user = _superuser()
    assert ChargerAssignmentService._get_assignments_by_unit({}, user=user) == {}

    unit = WirelessUnitFactory()
    first = PerformerAssignmentFactory(wireless_unit=unit, priority="critical")
    PerformerAssignmentFactory(wireless_unit=unit, priority="low")

    result = ChargerAssignmentService._get_assignments_by_unit(
        {unit.serial_number: unit, "ambiguous": None},
        user=user,
    )

    assert result == {unit.id: first}


def test_wall_serializer_keeps_empty_sections_and_nonempty_chargers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prefetched wall graphs serialize without dropping empty layout sections."""
    slot = SimpleNamespace(device_serial="unit", slot_number=1, charger_id=3)
    missing_slot = SimpleNamespace(device_serial="missing", slot_number=2, charger_id=3)
    unassigned_slot = SimpleNamespace(device_serial="unassigned", slot_number=3, charger_id=3)
    charger = SimpleNamespace(
        id=3,
        name="Charger",
        location_id=4,
        occupied_slots=[slot, missing_slot, unassigned_slot],
    )
    empty_charger = SimpleNamespace(
        id=4,
        name="Empty",
        location_id=4,
        occupied_slots=[],
    )
    section = SimpleNamespace(
        id=1,
        name="Main",
        layout="grid",
        columns=2,
        visible_chargers=[charger, empty_charger],
    )
    empty_section = SimpleNamespace(
        id=2,
        name="Spare",
        layout="list",
        columns=1,
        visible_chargers=[],
    )
    unit = SimpleNamespace(id=2)
    unassigned_unit = SimpleNamespace(id=3)
    assignment = object()
    serialize = Mock(return_value={"performer_name": "Singer"})
    monkeypatch.setattr(ChargerAssignmentService, "_serialize_performer_for_slot", serialize)

    result = ChargerAssignmentService._serialize_wall_sections(
        [section, empty_section],
        {"unit": unit, "unassigned": unassigned_unit},
        {unit.id: assignment},
    )

    assert result[0]["performers"][0]["performers"] == [{"performer_name": "Singer"}]
    assert result[1]["performers"] == []
    serialize.assert_called_once_with(slot, unit, assignment)


def test_missing_display_wall_returns_empty_payload() -> None:
    """Unknown wall IDs have a stable empty display contract."""
    assert ChargerAssignmentService.get_display_wall_data(999_999, user=_superuser()) == {}
