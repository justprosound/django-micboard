"""Factories for the physical location hierarchy."""

from __future__ import annotations

from typing import Any

import factory

from micboard.models.locations.structure import Building, Location, Room

from .base import ProjectModelFactory
from .registry import register_factory


@register_factory("micboard.Building")
class BuildingFactory(ProjectModelFactory):
    """Create a building without requiring optional multitenancy models."""

    class Meta:
        model = Building

    name = factory.Sequence(lambda number: f"Building {number}")
    address = factory.Sequence(lambda number: f"{number + 1} Example Avenue")
    country = "ZZ"
    regulatory_domain = factory.SubFactory(
        "tests.factories.rf_coordination.RegulatoryDomainFactory",
        country_code=factory.SelfAttribute("..country"),
    )


@register_factory("micboard.Room")
class RoomFactory(ProjectModelFactory):
    """Create a room in a unique building."""

    class Meta:
        model = Room

    building = factory.SubFactory("tests.factories.locations.BuildingFactory")
    name = factory.Sequence(lambda number: f"Room {number}")
    floor = "1"


@register_factory("micboard.Location")
class LocationFactory(ProjectModelFactory):
    """Create a location whose room belongs to the same building."""

    class Meta:
        model = Location

    building = factory.SubFactory("tests.factories.locations.BuildingFactory")
    room = factory.SubFactory(
        "tests.factories.locations.RoomFactory",
        building=factory.SelfAttribute("..building"),
    )
    name = factory.Sequence(lambda number: f"Location {number}")

    @classmethod
    def _generate(cls, strategy: str, params: dict[str, Any]) -> Location:
        """Derive the building when callers provide an existing room."""
        room = params.get("room")
        if room is not None and "building" not in params:
            params = {**params, "building": room.building}
        return super()._generate(strategy, params)

    @classmethod
    def _adjust_kwargs(cls, **kwargs: Any) -> dict[str, Any]:
        """Reject an explicitly inconsistent room and building."""
        room = kwargs.get("room")
        building = kwargs.get("building")
        if room is not None and building is not None and room.building != building:
            raise ValueError("Location room must belong to its building")
        return super()._adjust_kwargs(**kwargs)
