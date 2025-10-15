"""
Location and monitoring models for the micboard app.
"""

from typing import ClassVar

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Location(models.Model):
    """
    Represents a physical location (building/room).
    Can be linked to your existing location model using GenericForeignKey
    or you can add a ForeignKey to your specific model.
    """

    # Option 1: Generic foreign key to any location model
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Link to your external location model (e.g., Building, Room)",
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    external_location = GenericForeignKey("content_type", "object_id")

    # Option 2: Simple location fields (if you don't have an external model)
    building = models.CharField(max_length=100, blank=True, help_text="Building name")
    room = models.CharField(max_length=100, blank=True, help_text="Room name or number")
    floor = models.CharField(max_length=50, blank=True, help_text="Floor information")

    # Common fields
    name = models.CharField(max_length=200, help_text="Display name for this location")
    description = models.TextField(blank=True, help_text="Detailed description of the location")
    is_active = models.BooleanField(
        default=True, help_text="Whether this location is currently active"
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this location was created")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last update timestamp")

    class Meta:
        verbose_name = "Location"
        verbose_name_plural = "Locations"
        ordering: ClassVar[list[str]] = ["building", "room"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["building", "room"]),
        ]

    def __str__(self) -> str:
        if self.building and self.room:
            return f"{self.building} - {self.room}"
        return str(self.name)

    @property
    def full_address(self) -> str:
        """Get full location address"""
        parts: list[str] = []
        if self.building:
            parts.append(self.building)
        if self.floor:
            parts.append(f"Floor {self.floor}")
        if self.room:
            parts.append(self.room)
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
    location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="monitoring_groups",
        help_text="Physical location associated with this group",
    )
    users = models.ManyToManyField(
        "auth.User",
        related_name="monitoring_groups",
        blank=True,
        help_text="Users who are part of this monitoring group",
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
