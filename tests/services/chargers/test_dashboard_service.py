"""Query and projection contracts for the charger dashboard."""

from __future__ import annotations

from unittest.mock import patch

from django.template.loader import render_to_string

import pytest

from micboard.services.chargers import dashboard_service
from micboard.services.chargers.dashboard_dtos import (
    ChargerDashboardChargerSnapshot,
    ChargerDashboardPerformerSnapshot,
    ChargerDashboardSlotSnapshot,
    ChargerDashboardSnapshot,
)
from micboard.services.chargers.dashboard_service import ChargerDashboardService
from tests.factories.base import UserFactory
from tests.factories.hardware import ChargerFactory, ChargerSlotFactory, WirelessUnitFactory
from tests.factories.locations import LocationFactory
from tests.factories.monitoring import MonitoringGroupFactory, PerformerAssignmentFactory

pytestmark = pytest.mark.django_db


def test_snapshot_projects_prefetched_slots_and_only_occupied_performers(
    django_assert_num_queries,
) -> None:
    """The dashboard emits primitives from three queries regardless of unrelated assignments."""
    user = UserFactory(is_superuser=True)
    charger = ChargerFactory(
        is_active=True,
        name="Stage charger",
        model="CHG-2",
        ip="192.0.2.40",
    )
    ChargerSlotFactory(charger=charger, slot_number=1, occupied=False)
    ChargerSlotFactory(
        charger=charger,
        slot_number=2,
        occupied=True,
        device_serial="OCCUPIED-UNIT",
        device_model="TX-2",
        battery_percent=81,
        device_status="charging",
    )
    occupied_unit = WirelessUnitFactory(serial_number="OCCUPIED-UNIT")
    PerformerAssignmentFactory(
        wireless_unit=occupied_unit,
        performer__name="Visible performer",
        performer__title="Lead",
    )
    unrelated_unit = WirelessUnitFactory(serial_number="UNRELATED-UNIT")
    PerformerAssignmentFactory(
        wireless_unit=unrelated_unit,
        performer__name="Unrelated performer",
    )

    with django_assert_num_queries(3):
        snapshot = ChargerDashboardService.get_snapshot(user=user)

    assert snapshot.model_dump() == {
        "chargers": [
            {
                "id": charger.pk,
                "name": "Stage charger",
                "model_name": "CHG-2",
                "ip_address": "192.0.2.40",
                "slots": [
                    {
                        "slot_number": 1,
                        "occupied": False,
                        "device_serial": "",
                        "device_model": "",
                        "battery_percent": None,
                        "device_firmware_version": "",
                        "device_status": "",
                        "is_functional": True,
                        "performer": None,
                    },
                    {
                        "slot_number": 2,
                        "occupied": True,
                        "device_serial": "OCCUPIED-UNIT",
                        "device_model": "TX-2",
                        "battery_percent": 81,
                        "device_firmware_version": "",
                        "device_status": "charging",
                        "is_functional": True,
                        "performer": {
                            "name": "Visible performer",
                            "title": "Lead",
                            "photo_url": None,
                        },
                    },
                ],
                "slots_truncated": False,
                "slot_limit": 32,
            }
        ],
        "chargers_truncated": False,
        "charger_limit": 64,
    }


def test_snapshot_skips_assignment_lookup_without_occupied_serials(
    django_assert_num_queries,
) -> None:
    """An empty charger grid performs only charger and slot reads."""
    user = UserFactory(is_superuser=True)
    charger = ChargerFactory(is_active=True)
    ChargerSlotFactory(charger=charger, occupied=False)

    with (
        patch(
            "micboard.services.chargers.dashboard_service."
            "PerformerAssignmentService.get_preferred_active_assignments_for_serials"
        ) as for_user,
        django_assert_num_queries(2),
    ):
        snapshot = ChargerDashboardService.get_snapshot(user=user)

    for_user.assert_not_called()
    assert snapshot.chargers[0].slots[0].performer is None


def test_snapshot_bounds_visible_chargers_and_slots_before_projection(
    django_assert_num_queries,
    monkeypatch,
) -> None:
    """Tenant filtering precedes deterministic charger and slot cutoffs."""
    monkeypatch.setattr(dashboard_service, "MAX_DASHBOARD_CHARGERS", 2)
    monkeypatch.setattr(dashboard_service, "MAX_DASHBOARD_SLOTS_PER_CHARGER", 2)
    user = UserFactory()
    visible_location = LocationFactory()
    foreign_location = LocationFactory()
    group = MonitoringGroupFactory()
    group.users.add(user)
    group.locations.add(visible_location)

    for index in range(2):
        ChargerFactory(
            location=foreign_location,
            name=f"A foreign {index}",
            order=0,
            is_active=True,
        )
    visible_chargers = [
        ChargerFactory(
            location=visible_location,
            name=f"Visible {index}",
            order=index + 10,
            is_active=True,
        )
        for index in range(3)
    ]
    for charger in visible_chargers:
        for slot_number in (3, 1, 2):
            ChargerSlotFactory(charger=charger, slot_number=slot_number)

    with django_assert_num_queries(2):
        snapshot = ChargerDashboardService.get_snapshot(user=user)

    assert [charger.name for charger in snapshot.chargers] == ["Visible 0", "Visible 1"]
    assert snapshot.chargers_truncated is True
    assert snapshot.charger_limit == 2
    assert [slot.slot_number for slot in snapshot.chargers[0].slots] == [1, 2]
    assert snapshot.chargers[0].slots_truncated is True
    assert snapshot.chargers[0].slot_limit == 2


def test_grid_template_renders_nested_primitive_snapshot() -> None:
    """The template consumes nested DTO fields without an ORM relation manager."""
    snapshot = ChargerDashboardSnapshot(
        chargers=[
            ChargerDashboardChargerSnapshot(
                id=4,
                name="Primitive charger",
                model_name="CHG-4",
                ip_address="192.0.2.44",
                slots=[
                    ChargerDashboardSlotSnapshot(
                        slot_number=1,
                        occupied=True,
                        device_serial="SERIAL-4",
                        device_model="TX-4",
                        battery_percent=75,
                        device_firmware_version="4.0",
                        device_status="updating",
                        is_functional=True,
                        performer=ChargerDashboardPerformerSnapshot(
                            name="Primitive performer",
                            title="Lead",
                            photo_url=None,
                        ),
                    )
                ],
                slots_truncated=True,
                slot_limit=1,
            )
        ],
        chargers_truncated=True,
        charger_limit=1,
    )

    rendered = render_to_string(
        "micboard/partials/charger_grid.html",
        {"snapshot": snapshot},
    )

    assert "Primitive charger" in rendered
    assert "Primitive performer" in rendered
    assert "Firmware: 4.0" in rendered
    assert "Showing the first 1 chargers" in rendered
    assert "Showing the first 1 slots" in rendered
