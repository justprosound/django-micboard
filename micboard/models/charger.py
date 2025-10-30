from __future__ import annotations

from datetime import timedelta
from typing import ClassVar

from django.db import models
from django.utils import timezone


class ChargerSlot(models.Model):
    """Represents a charging slot in a charger station."""

    charger = models.ForeignKey(
        "micboard.Charger",
        on_delete=models.CASCADE,
        related_name="slots",
        help_text="The charger this slot belongs to",
    )
    slot_number = models.PositiveIntegerField(help_text="Slot number within the charger")
    transmitter = models.OneToOneField(
        "micboard.Transmitter",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="charger_slot",
        help_text="Transmitter currently in this slot",
    )
    is_occupied = models.BooleanField(default=False, help_text="Whether the slot has a transmitter")
    charging_status = models.BooleanField(default=False, help_text="Whether charging is active")

    class Meta:
        verbose_name = "Charger Slot"
        verbose_name_plural = "Charger Slots"
        ordering: ClassVar[list[str]] = ["charger", "slot_number"]
        unique_together: ClassVar[list[list[str]]] = [["charger", "slot_number"]]

    def __str__(self) -> str:
        return f"Slot {self.slot_number} in {self.charger}"


class ChargerManager(models.Manager):
    """Custom manager for Charger model"""

    def active(self):
        return self.filter(is_active=True)

    def online_recently(self, minutes=30):
        threshold = timezone.now() - timedelta(minutes=minutes)
        return self.filter(last_seen__gte=threshold, is_active=True)


class Charger(models.Model):
    """Represents a networked charging station."""

    DEVICE_TYPES: ClassVar[list[tuple[str, str]]] = [
        ("SBC250", "SBC 250"),
        ("SBC850", "SBC 850"),
        ("MXWNCS8", "MXW NCS 8"),
        ("MXWNCS4", "MXW NCS 4"),
        ("SBC220", "SBC 220"),
    ]

    # Manufacturer and API fields
    manufacturer = models.ForeignKey(
        "micboard.Manufacturer",
        on_delete=models.CASCADE,
        help_text="The manufacturer of this charger",
    )
    api_device_id = models.CharField(
        max_length=100,
        help_text="Unique identifier from the manufacturer's API",
    )
    ip = models.GenericIPAddressField(
        protocol="both", unique=True, help_text="IP address of the charger"
    )
    device_type = models.CharField(max_length=10, choices=DEVICE_TYPES, help_text="Type of charger")
    name = models.CharField(
        max_length=100, blank=True, help_text="Human-readable name for the charger"
    )
    firmware_version = models.CharField(
        max_length=50, blank=True, help_text="Firmware version of the charger"
    )
    location = models.ForeignKey(
        "micboard.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chargers",
        help_text="The physical location of this charger",
    )
    order = models.PositiveIntegerField(default=0, help_text="Display order for charger layouts")

    # Status fields
    is_active = models.BooleanField(
        default=True, help_text="Whether this charger is currently active/online"
    )
    last_seen = models.DateTimeField(
        null=True, blank=True, help_text="Last time this charger was successfully polled"
    )

    objects = ChargerManager()

    class Meta:
        verbose_name = "Charger"
        verbose_name_plural = "Chargers"
        ordering: ClassVar[list[str]] = ["order", "manufacturer__name", "name"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["manufacturer", "api_device_id"]),
            models.Index(fields=["is_active", "last_seen"]),
        ]
        unique_together: ClassVar[list[list[str]]] = [["manufacturer", "api_device_id"]]

    def __str__(self) -> str:
        return f"{self.manufacturer.name} {self.device_type} - {self.name} ({self.ip})"

    def mark_online(self) -> None:
        """Mark charger as online"""
        self.is_active = True
        self.last_seen = timezone.now()
        self.save(update_fields=["is_active", "last_seen"])

    def mark_offline(self) -> None:
        """Mark charger as offline"""
        self.is_active = False
        self.save(update_fields=["is_active"])

    def get_occupied_slots(self):
        """Get all occupied slots"""
        return self.slots.filter(is_occupied=True).select_related("transmitter")

    def get_slot_count(self) -> int:
        """Get total number of slots"""
        return self.slots.count()  # type: ignore

    @property
    def health_status(self) -> str:
        """Get health status based on last_seen and is_active"""
        if not self.is_active:
            return "offline"
        if not self.last_seen:
            return "unknown"
        from datetime import timedelta

        time_since = timezone.now() - self.last_seen
        if time_since < timedelta(minutes=5):
            return "healthy"
        if time_since < timedelta(minutes=30):
            return "warning"
        return "stale"

    @property
    def is_healthy(self) -> bool:
        """Check if charger is healthy"""
        return self.health_status == "healthy"
