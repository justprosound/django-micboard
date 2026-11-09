"""The external room key lets a host project join micboard rooms to its own rooms."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.loader import MigrationLoader

import pytest

from micboard.models.locations.structure import Room
from tests.factories.locations import BuildingFactory, RoomFactory

pytestmark = pytest.mark.django_db


def test_external_room_id_is_optional_and_blank_by_default() -> None:
    """Rooms need no host-project key, and many rooms may leave it unset."""
    first = RoomFactory()
    second = RoomFactory(building=first.building)

    assert first.external_room_id == ""
    assert second.external_room_id == ""
    first.full_clean()
    second.full_clean()


def test_unsaved_room_has_a_blank_external_room_id() -> None:
    """A new room reads as blank before it is saved, not as a database-default placeholder."""
    room = Room(building=BuildingFactory.build(), name="Unsaved")

    assert room.external_room_id == ""


def test_rooms_resolve_by_external_room_id() -> None:
    """A host project finds the micboard room for one of its own room keys."""
    room = RoomFactory(external_room_id="ROOM-0042")
    RoomFactory(external_room_id="ROOM-0043")

    assert list(Room.objects.filter(external_room_id="ROOM-0042")) == [room]


def test_external_room_id_is_unique_within_a_building() -> None:
    """Two rooms in one building cannot claim the same host-project room."""
    room = RoomFactory(external_room_id="ROOM-0042")

    with pytest.raises(IntegrityError), transaction.atomic():
        RoomFactory(building=room.building, external_room_id="ROOM-0042")


def test_duplicate_external_room_id_fails_validation() -> None:
    """Forms and admin report a duplicate key instead of raising a database error."""
    room = RoomFactory(external_room_id="ROOM-0042")
    duplicate = Room(building=room.building, name="Other", external_room_id="ROOM-0042")

    with pytest.raises(ValidationError):
        duplicate.full_clean()


def test_same_external_room_id_may_appear_in_different_buildings() -> None:
    """Uniqueness is scoped to the building, so tenants may reuse a key."""
    first = RoomFactory(external_room_id="ROOM-0042")
    other_building = BuildingFactory()

    second = RoomFactory(building=other_building, external_room_id="ROOM-0042")

    assert first.external_room_id == second.external_room_id


def test_migration_keeps_a_database_default_for_external_room_id() -> None:
    """The migration leaves a column default, so workers on the previous release can insert rooms."""
    state = MigrationLoader(connection).project_state(("micboard", "0006_room_external_room_id"))
    field = state.apps.get_model("micboard", "Room")._meta.get_field("external_room_id")

    assert field.db_default == ""
