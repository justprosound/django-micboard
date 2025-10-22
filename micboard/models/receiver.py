from __future__ import annotations

from datetime import timedelta
from typing import ClassVar

from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q
from django.utils import timezone


class UserFilteredReceiverQuerySet(models.QuerySet):
    """Custom queryset for Receiver model with user-based filtering."""

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
        q_objects = Q(location__in=user_locations)  # Specific locations

        # Add conditions for all rooms within a building
        if user_all_room_buildings:
            q_objects |= Q(location__building__in=user_all_room_buildings)

        return self.filter(q_objects).distinct()

    def filter_by_manufacturer_code(self, manufacturer_code: str | None):
        """Filter queryset by manufacturer code if provided."""
        if manufacturer_code:
            return self.filter(manufacturer__code=manufacturer_code)
        return self

    def active(self):
        """Get all active receivers"""
        return self.filter(is_active=True)

    def inactive(self):
        """Get all inactive receivers"""
        return self.filter(is_active=False)

    def online_recently(self, minutes=30):
        """Get receivers seen within the last N minutes"""
        threshold = timezone.now() - timedelta(minutes=minutes)
        return self.filter(last_seen__gte=threshold, is_active=True)

    def by_type(self, device_type):
        """Get receivers by device type"""
        return self.filter(device_type=device_type)

    def by_manufacturer(self, manufacturer):
        """Get receivers by manufacturer"""
        if isinstance(manufacturer, str):
            return self.filter(manufacturer__code=manufacturer)
        return self.filter(manufacturer=manufacturer)


class ReceiverManager(models.Manager):
    """Custom manager for Receiver model"""

    def get_queryset(self):
        return UserFilteredReceiverQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()

    def inactive(self):
        return self.get_queryset().inactive()

    def online_recently(self, minutes=30):
        return self.get_queryset().online_recently(minutes)

    def by_type(self, device_type):
        return self.get_queryset().by_type(device_type)

    def by_manufacturer(self, manufacturer):
        return self.get_queryset().by_manufacturer(manufacturer)

    def for_user(self, user: User):
        return self.get_queryset().for_user(user)


class Receiver(models.Model):
    """Represents a physical wireless receiver unit."""

    DEVICE_TYPES: ClassVar[list[tuple[str, str]]] = [
        ("uhfr", "UHF-R"),
        ("qlxd", "QLX-D"),
        ("ulxd", "ULX-D"),
        ("axtd", "Axient Digital"),
        ("p10t", "P10T"),
        # "offline" is a status, not a type. Removed from here.
    ]

    # Manufacturer and API fields
    manufacturer = models.ForeignKey(
        "micboard.Manufacturer",
        on_delete=models.CASCADE,
        help_text="The manufacturer of this device",
    )
    api_device_id = models.CharField(
        max_length=100,
        help_text="Unique identifier from the manufacturer's API",
    )
    ip = models.GenericIPAddressField(
        protocol="both", unique=True, help_text="IP address of the device"
    )
    device_type = models.CharField(max_length=10, choices=DEVICE_TYPES, help_text="Type of device")
    name = models.CharField(
        max_length=100, blank=True, help_text="Human-readable name for the device"
    )
    firmware_version = models.CharField(
        max_length=50, blank=True, help_text="Firmware version of the device"
    )
    location = models.ForeignKey(
        "micboard.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receivers",
        help_text="The physical location of this receiver",
    )
    order = models.PositiveIntegerField(default=0, help_text="Display order for charger layouts")
    # Status fields
    is_active = models.BooleanField(
        default=True, help_text="Whether this device is currently active/online"
    )
    last_seen = models.DateTimeField(
        null=True, blank=True, help_text="Last time this device was successfully polled"
    )

    objects = ReceiverManager()

    class Meta:
        verbose_name = "Receiver"
        verbose_name_plural = "Receivers"
        ordering: ClassVar[list[str]] = ["order", "manufacturer__name", "name"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["manufacturer", "api_device_id"]),
            models.Index(fields=["is_active", "last_seen"]),
        ]
        unique_together: ClassVar[list[list[str]]] = [["manufacturer", "api_device_id"]]

    def __str__(self) -> str:
        return f"{self.manufacturer.name} {self.device_type} - {self.name} ({self.ip})"

    def mark_online(self) -> None:
        """Mark receiver as online"""
        self.is_active = True
        self.last_seen = timezone.now()
        self.save(update_fields=["is_active", "last_seen"])

    def mark_offline(self) -> None:
        """Mark receiver as offline"""
        self.is_active = False
        self.save(update_fields=["is_active"])

    def get_active_channels(self):
        """Get all channels with active transmitters"""
        return self.channels.filter(transmitter__isnull=False).select_related("transmitter")

    def get_channel_count(self) -> int:
        """Get total number of channels"""
        return self.channels.count()  # type: ignore

    @property
    def health_status(self) -> str:
        """Get health status based on last_seen and is_active"""
        if not self.is_active:
            return "offline"
        if not self.last_seen:
            return "unknown"
        time_since = timezone.now() - self.last_seen
        if time_since < timedelta(minutes=5):
            return "healthy"
        if time_since < timedelta(minutes=30):
            return "warning"
        return "stale"

    @property
    def is_healthy(self) -> bool:
        """Check if receiver is healthy"""
        return self.health_status == "healthy"
