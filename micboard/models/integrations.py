"""Integration models for managing external manufacturer API connections."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models


class ManufacturerAPIServer(models.Model):
    """Manage multiple API servers per manufacturer across different locations."""

    class Manufacturer(models.TextChoices):
        """Supported manufacturers."""

        SHURE = "shure", "Shure System API"
        DANTE = "dante", "Dante"
        QSC = "qsc", "QSC"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        """Status of API server connection."""

        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        ERROR = "error", "Connection Error"
        UNKNOWN = "unknown", "Unknown"

    # Identity
    name = models.CharField(
        max_length=100, unique=True, help_text="Friendly name (e.g., 'Main Venue', 'Branch Office')"
    )
    manufacturer = models.CharField(max_length=20, choices=Manufacturer.choices)

    # Connection
    base_url = models.URLField(help_text="API endpoint URL (e.g., https://api.shure.local:10000)")
    shared_key = models.CharField(max_length=255, help_text="API authentication key/shared secret")
    verify_ssl = models.BooleanField(default=True, help_text="Verify SSL certificate")

    # Organization
    location_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Physical location name (e.g., 'Main Stage', 'Broadcast Center')",
    )

    # Status
    enabled = models.BooleanField(default=True, help_text="Enable/disable this API server")
    last_health_check = models.DateTimeField(
        null=True, blank=True, help_text="Last successful connection test"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UNKNOWN,
        help_text="Current connection status",
    )
    status_message = models.TextField(blank=True, help_text="Last error or status message")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, help_text="Internal notes about this server")

    class Meta:
        verbose_name = "Manufacturer API Server"
        verbose_name_plural = "Manufacturer API Servers"
        ordering = ["enabled", "-created_at"]
        indexes = [
            models.Index(fields=["manufacturer", "enabled"]),
            models.Index(fields=["location_name", "enabled"]),
        ]

    def __str__(self) -> str:
        location_str = f" ({self.location_name})" if self.location_name else ""
        status_icon = "✓" if self.enabled else "✗"
        return f"{status_icon} {self.name} - {self.get_manufacturer_display()}{location_str}"

    def clean(self) -> None:
        """Validate API server configuration."""
        if self.shared_key and len(self.shared_key.strip()) < 10:
            raise ValidationError({"shared_key": "API key must be at least 10 characters"})

    def to_config_dict(self) -> dict:
        """Convert to configuration dict format for API client initialization."""
        return {
            "manufacturer": self.manufacturer,
            "base_url": self.base_url,
            "shared_key": self.shared_key,
            "verify_ssl": self.verify_ssl,
            "location_name": self.location_name,
            "enabled": self.enabled,
        }


class Accessory(models.Model):
    """Track field unit accessories like lav mics, packs, IEM earbuds, etc."""

    class Category(models.TextChoices):
        """Accessory categories."""

        MICROPHONE = "microphone", "Microphone"
        PACK = "pack", "Wireless Pack/Bodypack"
        EARBUDS = "earbuds", "IEM Earbuds"
        ANTENNA = "antenna", "Antenna"
        CABLE = "cable", "Cable/Connector"
        POWER = "power", "Power/Battery"
        MOUNT = "mount", "Mount/Stand"
        CASE = "case", "Case/Bag"
        OTHER = "other", "Other"

    class Condition(models.TextChoices):
        """Accessory condition states."""

        EXCELLENT = "excellent", "Excellent"
        GOOD = "good", "Good"
        FAIR = "fair", "Fair"
        NEEDS_REPAIR = "needs_repair", "Needs Repair"
        UNKNOWN = "unknown", "Unknown"

    # Identity
    name = models.CharField(
        max_length=150, help_text="Accessory model/name (e.g., 'Shure SM7B Microphone')"
    )
    sku = models.CharField(
        max_length=50, blank=True, help_text="Manufacturer SKU or internal part number"
    )
    category = models.CharField(max_length=20, choices=Category.choices)

    # Assignment
    chassis = models.ForeignKey(
        "micboard.WirelessChassis",
        on_delete=models.CASCADE,
        related_name="accessories",
        help_text="Primary receiver/device this accessory is assigned to",
    )
    assigned_to = models.CharField(
        max_length=200,
        blank=True,
        help_text="Talent name, performer, or role (e.g., 'Lead Singer', 'Monitor Tech')",
    )

    # Condition & maintenance
    condition = models.CharField(
        max_length=20, choices=Condition.choices, default=Condition.UNKNOWN
    )
    notes = models.TextField(blank=True, help_text="Usage notes, known issues, maintenance history")
    is_available = models.BooleanField(
        default=True, help_text="Available for use (not broken/missing)"
    )

    # Tracking
    serial_number = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Manufacturer serial number for individual tracking",
    )
    checked_out_date = models.DateTimeField(
        null=True, blank=True, help_text="When this accessory was last checked out"
    )
    checked_in_date = models.DateTimeField(
        null=True, blank=True, help_text="When this accessory was last checked in"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Accessory"
        verbose_name_plural = "Accessories"
        ordering = ["chassis", "category", "name"]
        indexes = [
            models.Index(fields=["chassis", "category"]),
            models.Index(fields=["serial_number"]),
            models.Index(fields=["assigned_to"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["chassis", "serial_number"],
                condition=models.Q(serial_number__gt=""),
                name="unique_serial_per_chassis",
            )
        ]

    def __str__(self) -> str:
        status = "✓" if self.is_available else "✗"
        assigned = f" → {self.assigned_to}" if self.assigned_to else ""
        return f"{status} {self.get_category_display()}: {self.name}{assigned}"

    @property
    def status_display(self) -> str:
        """Human-readable status."""
        if not self.is_available:
            return "🚫 Unavailable"
        if self.condition == "needs_repair":
            return "⚠️ Needs Repair"
        return "✓ Available"
