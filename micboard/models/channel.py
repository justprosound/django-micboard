from __future__ import annotations

from typing import ClassVar

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q


class UserFilteredChannelQuerySet(models.QuerySet):
    """Custom queryset for Channel model with user-based filtering."""

    def for_user(self, user: User):
        if user.is_superuser:
            return self

        # Get all locations associated with the user's monitoring groups
        user_locations = user.monitoring_groups.filter(is_active=True).values_list(
            "monitoringgrouplocation__location", flat=True
        )
        # Get all buildings where the user has access to all rooms
        user_all_room_buildings = user.monitoring_groups.filter(
            is_active=True, monitoringgrouplocation__include_all_rooms=True
        ).values_list("monitoringgrouplocation__location__building", flat=True)

        # Build a Q object for filtering
        q_objects = Q(receiver__location__in=user_locations)  # Specific locations

        # Add conditions for all rooms within a building
        if user_all_room_buildings:
            q_objects |= Q(receiver__location__building__in=user_all_room_buildings)

        return self.filter(q_objects).distinct()


class ChannelManager(models.Manager):
    """Custom manager for Channel model"""

    def get_queryset(self):
        return UserFilteredChannelQuerySet(self.model, using=self._db)

    def for_user(self, user: User):
        return self.get_queryset().for_user(user)


class Channel(models.Model):
    """Represents an individual channel on a Shure wireless receiver."""

    receiver = models.ForeignKey(
        "micboard.Receiver",
        on_delete=models.CASCADE,
        related_name="channels",
        help_text="The receiver this channel belongs to",
    )
    channel_number = models.PositiveIntegerField(help_text="Channel number on the receiver")
    # Optional current frequency for the channel (e.g., 584.000)
    frequency = models.FloatField(
        null=True, blank=True, help_text="Operating frequency for this channel"
    )
    image = models.ImageField(
        upload_to="channel_images/",
        null=True,
        blank=True,
        help_text="Reusable image assigned to this channel",
    )

    objects = ChannelManager()

    class Meta:
        verbose_name = "Channel"
        verbose_name_plural = "Channels"
        unique_together: ClassVar[list[list[str]]] = [["receiver", "channel_number"]]
        ordering: ClassVar[list[str]] = ["receiver__name", "channel_number"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["receiver", "channel_number"]),
        ]

    def __str__(self) -> str:
        return f"{self.receiver.name} - Channel {self.channel_number}"

    def has_transmitter(self) -> bool:
        """Check if this channel has a transmitter assigned"""
        return hasattr(self, "transmitter")

    def get_transmitter_name(self) -> str:
        """Get transmitter name or empty string"""
        if self.has_transmitter():
            return self.transmitter.name or f"Slot {self.transmitter.slot}"
        return ""
