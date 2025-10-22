from __future__ import annotations

from typing import ClassVar

from django.db import models


class Building(models.Model):
    """Represents a physical building."""

    name = models.CharField(max_length=100, unique=True, help_text="Name of the building")
    address = models.CharField(
        max_length=255, blank=True, help_text="Physical address of the building"
    )
    description = models.TextField(blank=True, help_text="Detailed description of the building")

    class Meta:
        verbose_name = "Building"
        verbose_name_plural = "Buildings"
        ordering: ClassVar[list[str]] = ["name"]

    def __str__(self) -> str:
        return str(self.name)


class Room(models.Model):
    """Represents a room within a building."""

    building = models.ForeignKey(
        Building,
        on_delete=models.CASCADE,
        related_name="rooms",
        help_text="The building this room belongs to",
    )
    name = models.CharField(max_length=100, help_text="Name or number of the room")
    floor = models.CharField(max_length=50, blank=True, help_text="Floor information")
    description = models.TextField(blank=True, help_text="Detailed description of the room")

    class Meta:
        verbose_name = "Room"
        verbose_name_plural = "Rooms"
        unique_together: ClassVar[list[list[str]]] = [["building", "name"]]
        ordering: ClassVar[list[str]] = ["building__name", "name"]

    def __str__(self) -> str:
        return f"{self.building.name} - {self.name}"


class Location(models.Model):
    """
    Represents a specific point of interest within a building and room.
    This model links to Building and Room for structured location management.
    """

    building = models.ForeignKey(
        Building,
        on_delete=models.CASCADE,
        related_name="locations",
        help_text="The building this location is in",
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name="locations",
        null=True,
        blank=True,
        help_text="The room this location is in (optional)",
    )
    name = models.CharField(max_length=200, help_text="Display name for this specific location")
    description = models.TextField(blank=True, help_text="Detailed description of the location")
    is_active = models.BooleanField(
        default=True, help_text="Whether this location is currently active"
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this location was created")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last update timestamp")

    class Meta:
        verbose_name = "Location"
        verbose_name_plural = "Locations"
        ordering: ClassVar[list[str]] = ["building__name", "room__name", "name"]
        unique_together: ClassVar[list[list[str]]] = [["building", "room", "name"]]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["building", "room"]),
        ]

    def __str__(self) -> str:
        if self.room:
            return f"{self.building.name} - {self.room.name} ({self.name})"
        return f"{self.building.name} ({self.name})"

    @property
    def full_address(self) -> str:
        """Get full location address"""
        parts: list[str] = []
        if self.building:
            parts.append(self.building.name)
        if self.room and self.room.floor:
            parts.append(f"Floor {self.room.floor}")
        if self.room:
            parts.append(self.room.name)
        return " - ".join(parts) if parts else str(self.name)


class MonitoringGroup(models.Model):
    """
    Represents a group of users who monitor specific devices together.
    Useful for organizing teams (e.g., "Theater Tech Team", "Conference Room A Staff")
    """

    name = models.CharField(
        max_length=100, unique=True, help_text="Unique name for the monitoring group"
    )
    description = models.TextField(blank=True, help_text="Description of the monitoring group")
    users = models.ManyToManyField(
        "auth.User",
        related_name="monitoring_groups",
        blank=True,
        help_text="Users who are part of this monitoring group",
    )
    locations = models.ManyToManyField(
        Location,
        through="MonitoringGroupLocation",
        related_name="monitoring_groups",
        blank=True,
        help_text="Locations assigned to this monitoring group",
    )
    channels = models.ManyToManyField(
        "Channel",
        related_name="monitoring_groups",
        blank=True,
        help_text="Channels assigned to this monitoring group",
    )
    is_active = models.BooleanField(
        default=True, help_text="Whether this monitoring group is active"
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this group was created")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last update timestamp")

    class Meta:
        verbose_name = "Monitoring Group"
        verbose_name_plural = "Monitoring Groups"
        ordering: ClassVar[list[str]] = ["name"]

    def __str__(self) -> str:
        return str(self.name)

    def get_active_users(self):
        """Get all active users in this group"""
        return self.users.filter(is_active=True)

    def get_active_channels(self):
        """Get all active channels in this group"""
        return self.channels.select_related("receiver").filter(receiver__is_active=True)


class MonitoringGroupLocation(models.Model):
    """
    Intermediary model for MonitoringGroup and Location, specifying access scope.
    """

    monitoring_group = models.ForeignKey(MonitoringGroup, on_delete=models.CASCADE)
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    include_all_rooms = models.BooleanField(
        default=False,
        help_text="If true, this group has access to all rooms within the specified building of the location.",
    )

    class Meta:
        unique_together: ClassVar[list[list[str]]] = [["monitoring_group", "location"]]
        verbose_name = "Monitoring Group Location"
        verbose_name_plural = "Monitoring Group Locations"

    def __str__(self) -> str:
        return f"{self.monitoring_group.name} - {self.location.full_address}"
