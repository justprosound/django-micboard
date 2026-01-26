"""Charger and charger slot models for wireless equipment charging and storage."""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from micboard.models.base_managers import TenantOptimizedManager, TenantOptimizedQuerySet


class ChargerQuerySet(TenantOptimizedQuerySet):
    """Enhanced queryset for Charger model with tenant filtering."""

    def by_location(self, *, location_id: int) -> ChargerQuerySet:
        return self.filter(location_id=location_id)

    def active(self) -> ChargerQuerySet:
        return self.filter(is_active=True)

    def with_inventory(self) -> ChargerQuerySet:
        return self.prefetch_related("slots")


class ChargerManager(TenantOptimizedManager):
    """Enhanced manager for Charger model with tenant support."""

    def get_queryset(self) -> ChargerQuerySet:
        return ChargerQuerySet(self.model, using=self._db)

    def by_location(self, *, location_id: int) -> ChargerQuerySet:
        return self.get_queryset().by_location(location_id=location_id)

    def active(self) -> ChargerQuerySet:
        return self.get_queryset().active()

    def with_inventory(self) -> ChargerQuerySet:
        return self.get_queryset().with_inventory()


class Charger(models.Model):
    """Charger unit for field wireless devices (bodypacks, handheld, IEM receivers)."""

    STATUS_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("discovered", "Discovered"),
        ("online", "Online"),
        ("offline", "Offline"),
        ("degraded", "Degraded"),
        ("maintenance", "Maintenance"),
        ("retired", "Retired"),
    ]

    location = models.ForeignKey(
        "micboard.Location",
        on_delete=models.CASCADE,
        related_name="chargers",
        help_text="Location where this charger is installed",
    )

    manufacturer = models.ForeignKey(
        "micboard.Manufacturer",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="The manufacturer of this charger",
    )

    model = models.CharField(
        max_length=100,
        blank=True,
        help_text="Charger model (e.g., 'Shure SBC941', 'Sennheiser CHR42')",
    )
    serial_number = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Charger serial number for tracking",
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Charger name/label (e.g., 'Charger A - Stage', 'Backup Charger')",
    )

    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order",
    )

    ip = models.GenericIPAddressField(
        protocol="both",
        unique=True,
        null=True,
        blank=True,
        help_text="IP address of the device",
    )

    slot_count = models.PositiveIntegerField(
        default=4,
        help_text="Number of charging slots on this charger",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this charger is active and in use",
    )

    status = models.CharField(
        max_length=20,
        default="discovered",
        choices=STATUS_CHOICES,
        help_text="Current lifecycle status",
    )

    device_type = models.CharField(
        max_length=20,
        default="charger",
        help_text="Device type (charger)",
    )

    firmware_version = models.CharField(
        max_length=50,
        blank=True,
        help_text="Charger firmware version",
    )

    last_seen = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this device was successfully polled",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ChargerManager()

    class Meta:
        verbose_name = "Charger"
        verbose_name_plural = "Chargers"
        ordering: ClassVar[list[str]] = ["location__name", "name"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["location", "is_active"]),
            models.Index(fields=["serial_number"]),
        ]

    def __str__(self) -> str:
        if self.name:
            return f"{self.name} at {self.location.name}"
        return f"Charger {self.model} ({self.serial_number}) at {self.location.name}"


class ChargerSlot(models.Model):
    """Individual charging slot on a charger unit.

    Decoupled from WirelessUnit to allow multiple different devices to dock
    over time without link rot.
    """

    charger = models.ForeignKey(
        Charger,
        on_delete=models.CASCADE,
        related_name="slots",
        help_text="The charger this slot belongs to",
    )

    slot_number = models.PositiveIntegerField(
        help_text="Slot number on the charger (1-based)",
    )

    occupied = models.BooleanField(
        default=False,
        help_text="Whether a device is currently in this slot",
    )

    # Local docked device metadata (Decoupled)
    device_serial = models.CharField(
        max_length=100,
        blank=True,
        help_text="Serial number of the device in this slot (if occupied)",
    )

    device_model = models.CharField(
        max_length=100,
        blank=True,
        help_text="Model of the device in this slot (if occupied)",
    )

    battery_percent = models.IntegerField(
        null=True,
        blank=True,
        help_text="Battery percentage of the docked device",
    )

    device_firmware_version = models.CharField(
        max_length=50,
        blank=True,
        help_text="Firmware version of the docked device",
    )

    device_status = models.CharField(
        max_length=50,
        blank=True,
        help_text="Status of the docked device (e.g., 'charging', 'updating')",
    )

    is_functional = models.BooleanField(
        default=True,
        help_text="Whether this slot is functional",
    )

    class Meta:
        verbose_name = "Charger Slot"
        verbose_name_plural = "Charger Slots"
        unique_together: ClassVar[list[list[str]]] = [["charger", "slot_number"]]
        ordering: ClassVar[list[str]] = ["charger", "slot_number"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["charger", "slot_number"]),
            models.Index(fields=["occupied"]),
        ]

    def __str__(self) -> str:
        status = "occupied" if self.occupied else "empty"
        content = (
            f" ({self.device_model} {self.device_serial})"
            if self.occupied and self.device_model
            else ""
        )
        return f"{self.charger.name} - Slot {self.slot_number} ({status}{content})"
