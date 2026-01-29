"""Location hierarchy models for physical device placement tracking.

Provides three-tier location structure: Building > Room > Location.
Used for device assignment, movement tracking, and spatial organization.

Optional multi-tenancy support:
- MICBOARD_MULTI_SITE_MODE: Adds site FK to Building
- MICBOARD_MSP_ENABLED: Adds organization and campus FKs to Building
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.contrib.sites.models import Site
from django.db import models


class Building(models.Model):
    """Represents a physical building.

    Multi-tenancy support:
    - site: Optional Django Site FK (when MICBOARD_MULTI_SITE_MODE=True)
    - organization: Optional Organization FK (when MICBOARD_MSP_ENABLED=True)
    - campus: Optional Campus FK (when MICBOARD_MSP_ENABLED=True)
    """

    name = models.CharField(max_length=100, help_text="Name of the building")
    address = models.CharField(
        max_length=255, blank=True, help_text="Physical address of the building"
    )
    country = models.CharField(
        max_length=2,
        default="US",
        help_text="ISO 3166-1 alpha-2 country code (e.g., 'US', 'DE', 'AU')",
    )
    description = models.TextField(blank=True, help_text="Detailed description of the building")

    regulatory_domain = models.ForeignKey(
        "micboard.RegulatoryDomain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="buildings",
        help_text="Regulatory domain governing RF usage in this building",
    )

    site = models.ForeignKey(
        Site,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="buildings",
        help_text="Django Site this building belongs to (optional)",
    )

    # organization = models.ForeignKey(
    #     "micboard_multitenancy.Organization",
    #     on_delete=models.CASCADE,
    #     null=True,
    #     blank=True,
    #     related_name="buildings",
    #     help_text="Organization this building belongs to (optional)",
    # )
    # campus = models.ForeignKey(
    #     "micboard_multitenancy.Campus",
    #     on_delete=models.SET_NULL,
    #     null=True,
    #     blank=True,
    #     related_name="buildings",
    #     help_text="Campus this building belongs to (optional)",
    # )

    class Meta:
        verbose_name = "Building"
        verbose_name_plural = "Buildings"
        ordering: ClassVar[list[str]] = ["name"]

    def __str__(self) -> str:
        return str(self.name)

    @property
    def tenant_scope(self) -> str:
        """Get human-readable tenant scope for this building."""
        # if getattr(settings, "MICBOARD_MSP_ENABLED", False):
        #     if hasattr(self, "organization"):
        #         org_name = self.organization.name if self.organization else "No Org"
        #         campus_name = (
        #             f" - {self.campus.name}" if hasattr(self, "campus") and self.campus else ""
        #         )
        #         return f"{org_name}{campus_name}"
        if getattr(settings, "MICBOARD_MULTI_SITE_MODE", False):
            if hasattr(self, "site"):
                return f"Site: {self.site.name if self.site else 'Default'}"
        return "Single-Site"

    def save(self, *args, **kwargs) -> None:
        """Auto-assign regulatory domain based on country if not set."""
        from django.db import OperationalError, ProgrammingError

        from micboard.models.rf_coordination import RegulatoryDomain

        if self.country and not self.regulatory_domain:
            try:
                domain = RegulatoryDomain.objects.filter(country_code=self.country.upper()).first()
                if domain:
                    self.regulatory_domain = domain
            except (ProgrammingError, OperationalError):
                # Table doesn't exist yet (e.g., during migrations or tests)
                pass

        super().save(*args, **kwargs)


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
    """Represents a specific point of interest within a building and room.

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
        """Get full location address."""
        parts: list[str] = []
        if self.building:
            parts.append(self.building.name)
        if self.room and self.room.floor:
            parts.append(f"Floor {self.room.floor}")
        if self.room:
            parts.append(self.room.name)
        return " - ".join(parts) if parts else str(self.name)
