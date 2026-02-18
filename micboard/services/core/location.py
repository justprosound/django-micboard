"""Location service layer for location management and device organization.

Manages locations and provides location-based device queries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from django.db import models
from django.db.models import Count, QuerySet

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.locations.structure import Location
from micboard.services.shared.tenant_filters import apply_tenant_filters

if TYPE_CHECKING:  # pragma: no cover
    pass

_ModelT = TypeVar("_ModelT", bound=models.Model)


class LocationService:
    """Business logic for location management and organization."""

    @staticmethod
    def create_location(*, name: str, description: str = "") -> Location:
        """Create a new location.

        Args:
            name: Location name.
            description: Optional location description.

        Returns:
            Created Location object.

        Raises:
            ValueError: If location with same name already exists.
        """
        if Location.objects.filter(name=name).exists():
            msg = f"Location with name '{name}' already exists"
            raise ValueError(msg)

        return Location.objects.create(name=name, description=description)

    @staticmethod
    def update_location(
        *, location: Location, name: str | None = None, description: str | None = None
    ) -> Location:
        """Update a location.

        Args:
            location: Location instance.
            name: New name, or None to skip.
            description: New description, or None to skip.

        Returns:
            Updated Location object.
        """
        updated = False
        if name is not None and location.name != name:
            # Check for duplicates
            if Location.objects.filter(name=name).exclude(id=location.id).exists():
                msg = f"Location with name '{name}' already exists"
                raise ValueError(msg)
            location.name = name
            updated = True
        if description is not None and location.description != description:
            location.description = description
            updated = True

        if updated:
            location.save()

        return location

    @staticmethod
    def delete_location(*, location: Location) -> None:
        """Delete a location.

        All associated devices will have their location cleared.

        Args:
            location: Location instance to delete.
        """
        location.delete()

    @staticmethod
    def get_all_locations(
        *,
        organization_id: int | None = None,
        site_id: int | None = None,
        campus_id: int | None = None,
    ) -> QuerySet[Location]:
        """Get all locations.

        Args:
            organization_id: Optional organization ID (MSP mode).
            site_id: Optional site ID (multi-site mode).
            campus_id: Optional campus ID (MSP mode).

        Returns:
            QuerySet of Location objects ordered by name.
        """
        qs: QuerySet[Location] = Location.objects.all()
        return apply_tenant_filters(
            qs,
            organization_id=organization_id,
            campus_id=campus_id,
            site_id=site_id,
            building_path="building",
        ).order_by("name")

    @staticmethod
    def get_location_device_counts() -> QuerySet[Location]:
        """Get locations with their device counts.

        Returns:
            QuerySet of Location objects with annotated chassis count.
        """
        return Location.objects.annotate(chassis_count=Count("wireless_devices")).order_by(
            "-chassis_count"
        )

    @staticmethod
    def get_hardware_in_location(*, location: Location) -> QuerySet[WirelessChassis]:
        """Get all active devices in a location.

        Args:
            location: Location instance.

        Returns:
            QuerySet of WirelessChassis objects in the location.
        """
        return location.wireless_devices.filter(status="online")

    @staticmethod
    def assign_device_to_location(
        *, device: WirelessChassis, location: Location
    ) -> WirelessChassis:
        """Assign a device to a location.

        Args:
            device: WirelessChassis instance.
            location: Location instance.

        Returns:
            Updated WirelessChassis object.
        """
        device.location = location
        device.save(update_fields=["location"])
        return device

    @staticmethod
    def unassign_device_from_location(*, device: WirelessChassis) -> WirelessChassis:
        """Remove device from location.

        Args:
            device: WirelessChassis instance.

        Returns:
            Updated WirelessChassis object.
        """
        device.location = None
        device.save(update_fields=["location"])
        return device

    @staticmethod
    def list_all_locations() -> QuerySet[Location]:
        """Get all locations (alias for get_all_locations)."""
        return LocationService.get_all_locations()

    @staticmethod
    def get_location_by_id(location_id: int) -> Location | None:
        """Get a location by its ID."""
        try:
            return Location.objects.get(id=location_id)
        except Location.DoesNotExist:
            return None

    @staticmethod
    def count_total_locations() -> int:
        """Count total number of locations."""
        return Location.objects.count()

    @staticmethod
    def count_locations_with_devices() -> int:
        """Count locations that have devices assigned."""
        return Location.objects.filter(wireless_devices__isnull=False).distinct().count()

    # Async methods (Django 4.2+ async view support)

    @staticmethod
    async def acreate_location(*, name: str, description: str = ""):
        """Async: Create a new location.

        Args:
            name: Location name
            description: Optional description

        Returns:
            Created Location instance

        Raises:
            LocationAlreadyExistsError: If location with name already exists
        """
        from asgiref.sync import sync_to_async

        return await sync_to_async(LocationService.create_location)(
            name=name,
            description=description,
        )

    @staticmethod
    async def alist_all_locations():
        """Async: Get all locations.

        Returns:
            QuerySet of all Location instances
        """
        from asgiref.sync import sync_to_async

        return await sync_to_async(LocationService.list_all_locations)()

    @staticmethod
    async def aassign_device_to_location(*, device, location):
        """Async: Assign device to location.

        Args:
            device: WirelessChassis instance
            location: Location instance

        Returns:
            Updated WirelessChassis instance
        """
        from asgiref.sync import sync_to_async

        return await sync_to_async(LocationService.assign_device_to_location)(
            device=device,
            location=location,
        )
