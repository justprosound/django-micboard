"""Service-level tests for physical location management."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from django.test import override_settings

import pytest

from micboard.models.locations.structure import Location
from micboard.services.core.location import LocationService
from tests.factories.hardware import WirelessChassisFactory
from tests.factories.locations import BuildingFactory, LocationFactory, RoomFactory


@pytest.mark.django_db
def test_create_location_persists_required_hierarchy() -> None:
    """Create a location with its required building and optional room context."""
    building = BuildingFactory()
    room = RoomFactory(building=building)

    location = LocationService.create_location(
        building=building,
        room=room,
        name="Stage Left",
        description="Monitor position",
    )

    assert location.building == building
    assert location.room == room
    assert location.name == "Stage Left"
    assert location.description == "Monitor position"


@pytest.mark.django_db
def test_create_location_rejects_duplicate_name_in_same_hierarchy() -> None:
    """Reject duplicate locations where the database uniqueness scope matches."""
    existing = LocationFactory(name="Stage Left", room=None)

    with pytest.raises(ValueError, match="already exists"):
        LocationService.create_location(
            building=existing.building,
            room=existing.room,
            name=existing.name,
        )


@pytest.mark.django_db
def test_create_location_rejects_room_from_another_building() -> None:
    """Protect the required building and room hierarchy before persistence."""
    building = BuildingFactory()
    unrelated_room = RoomFactory()

    with pytest.raises(ValueError, match="room must belong"):
        LocationService.create_location(
            building=building,
            room=unrelated_room,
            name="Invalid hierarchy",
        )

    assert not Location.objects.filter(name="Invalid hierarchy").exists()


def test_async_create_location_preserves_required_hierarchy() -> None:
    """Forward building and room through the asynchronous service adapter."""
    building = BuildingFactory.build()
    room = RoomFactory.build(building=building)
    expected = LocationFactory.build(building=building, room=room)

    with patch.object(LocationService, "create_location", return_value=expected) as create:
        location = asyncio.run(
            LocationService.acreate_location(
                building=building,
                room=room,
                name="Async position",
                description="Created through the async facade",
            )
        )

    assert location is expected
    create.assert_called_once_with(
        building=building,
        name="Async position",
        room=room,
        description="Created through the async facade",
    )


@pytest.mark.django_db
def test_update_location_persists_changes_and_rejects_duplicate_name() -> None:
    """Persist changed values without allowing a conflicting location name."""
    location = LocationFactory(name="Old Position", description="Old description")
    conflicting = LocationFactory(
        building=location.building,
        room=location.room,
        name="Existing Position",
    )

    updated = LocationService.update_location(
        location=location,
        name="New Position",
        description="New description",
    )
    updated.refresh_from_db()
    assert updated.name == "New Position"
    assert updated.description == "New description"

    with pytest.raises(ValueError, match="already exists"):
        LocationService.update_location(location=updated, name=conflicting.name)


@pytest.mark.django_db
def test_update_location_skips_persistence_when_values_are_unchanged() -> None:
    """Avoid a write and timestamp churn for an idempotent update."""
    location = LocationFactory()

    with patch.object(Location, "save", autospec=True) as save:
        returned = LocationService.update_location(
            location=location,
            name=location.name,
            description=location.description,
        )

    assert returned.pk == location.pk
    save.assert_not_called()


@pytest.mark.django_db
def test_update_location_does_not_restore_fields_from_a_stale_instance() -> None:
    """Sequential stale callers only persist fields explicitly supplied by each caller."""
    location = LocationFactory(name="Original name", description="Original description")
    name_editor = Location.objects.get(pk=location.pk)
    description_editor = Location.objects.get(pk=location.pk)

    LocationService.update_location(location=name_editor, name="Current name")
    updated = LocationService.update_location(
        location=description_editor,
        description="Current description",
    )

    updated.refresh_from_db()
    assert updated.name == "Current name"
    assert updated.description == "Current description"


@pytest.mark.django_db
def test_delete_location_clears_assigned_chassis_location() -> None:
    """Honor the model's SET_NULL ownership contract when deleting a location."""
    location = LocationFactory()
    chassis = WirelessChassisFactory(location=location)

    LocationService.delete_location(location=location)

    assert not Location.objects.filter(pk=location.pk).exists()
    chassis.refresh_from_db()
    assert chassis.location is None


@pytest.mark.django_db
def test_location_queries_order_results_and_filter_online_hardware() -> None:
    """Return deterministic location ordering and only online local hardware."""
    zulu = LocationFactory(name="Zulu")
    alpha = LocationFactory(name="Alpha")
    online = WirelessChassisFactory(location=alpha, status="online")
    WirelessChassisFactory(location=alpha, status="offline")

    assert list(LocationService.get_all_locations()) == [alpha, zulu]
    assert list(LocationService.get_hardware_in_location(location=alpha)) == [online]


@override_settings(MICBOARD_MSP_ENABLED=True)
@pytest.mark.django_db
def test_get_all_locations_applies_organization_and_campus_scope() -> None:
    """Delegate MSP isolation to the shared tenant-filter contract."""
    matching = LocationFactory(
        building=BuildingFactory(organization_id=10, campus_id=20),
        room=None,
    )
    LocationFactory(
        building=BuildingFactory(organization_id=10, campus_id=21),
        room=None,
    )
    LocationFactory(
        building=BuildingFactory(organization_id=11, campus_id=20),
        room=None,
    )

    locations = LocationService.get_all_locations(organization_id=10, campus_id=20)

    assert list(locations) == [matching]


@pytest.mark.django_db
def test_location_device_counts_are_distinct_and_ordered_descending() -> None:
    """Annotate each location with chassis count and rank busiest first."""
    busiest = LocationFactory()
    quieter = LocationFactory()
    empty = LocationFactory()
    WirelessChassisFactory.create_batch(2, location=busiest)
    WirelessChassisFactory(location=quieter)

    rows = list(LocationService.get_location_device_counts())

    assert [(row.pk, row.chassis_count) for row in rows] == [
        (busiest.pk, 2),
        (quieter.pk, 1),
        (empty.pk, 0),
    ]


@pytest.mark.django_db
def test_assign_and_unassign_device_persist_location() -> None:
    """Move chassis into and out of a physical location."""
    chassis = WirelessChassisFactory(location=None)
    location = LocationFactory()

    assert LocationService.assign_device_to_location(device=chassis, location=location) == chassis
    chassis.refresh_from_db()
    assert chassis.location == location

    assert LocationService.unassign_device_from_location(device=chassis) == chassis
    chassis.refresh_from_db()
    assert chassis.location is None


@pytest.mark.django_db
def test_lookup_and_count_helpers_report_present_and_missing_rows() -> None:
    """Expose stable lookup and aggregate contracts for callers."""
    with_device = LocationFactory()
    empty = LocationFactory()
    WirelessChassisFactory.create_batch(2, location=with_device)

    assert LocationService.get_location_by_id(with_device.pk) == with_device
    assert LocationService.get_location_by_id(empty.pk + 10_000) is None
    assert LocationService.count_total_locations() == 2
    assert LocationService.count_locations_with_devices() == 1
