"""Display wall and kiosk models for stage/monitor display management."""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from micboard.models.base_managers import TenantOptimizedManager, TenantOptimizedQuerySet


class DisplayWallQuerySet(TenantOptimizedQuerySet):
    """Query helpers for display walls with tenant awareness."""

    def active(self) -> DisplayWallQuerySet:
        """Get all active display walls."""
        return self.filter(is_active=True)

    def by_location(self, *, location_id: int) -> DisplayWallQuerySet:
        """Filter by location."""
        return self.filter(location_id=location_id)

    def with_sections(self) -> DisplayWallQuerySet:
        """Optimize: prefetch sections."""
        return self.prefetch_related("sections")


class DisplayWallManager(TenantOptimizedManager):
    """Manager for display walls."""

    def get_queryset(self) -> DisplayWallQuerySet:
        return DisplayWallQuerySet(self.model, using=self._db)

    def active(self) -> DisplayWallQuerySet:
        return self.get_queryset().active()

    def by_location(self, *, location_id: int) -> DisplayWallQuerySet:
        return self.get_queryset().by_location(location_id=location_id)


class DisplayWall(models.Model):
    """Physical display kiosk/screen showing stage/charger status.

    Represents a single physical display (monitor/TV/kiosk) positioned in
    a venue showing real-time performer status, RF channel info, and battery
    levels. Multiple walls can exist in the same location (e.g., stage monitor,
    backstage display, FOH position).
    """

    ORIENTATION_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("landscape", "Landscape (16:9, 16:10)"),
        ("portrait", "Portrait (9:16, 10:16)"),
        ("square", "Square (1:1)"),
    ]

    location = models.ForeignKey(
        "micboard.Location",
        on_delete=models.CASCADE,
        related_name="display_walls",
        help_text="Location where this display is installed",
    )

    name = models.CharField(
        max_length=100,
        help_text="Display name (e.g., 'Stage Monitor Left', 'FOH Kiosk 1')",
    )

    # Kiosk ID for remote access
    kiosk_id = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique identifier for this kiosk (for remote displays)",
    )

    # Display properties
    display_width_px = models.PositiveIntegerField(
        default=1920,
        help_text="Native display width in pixels",
    )

    display_height_px = models.PositiveIntegerField(
        default=1080,
        help_text="Native display height in pixels",
    )

    orientation = models.CharField(
        max_length=20,
        choices=ORIENTATION_CHOICES,
        default="landscape",
        help_text="Display orientation",
    )

    # Content settings
    show_performer_photos = models.BooleanField(
        default=True,
        help_text="Show performer photos on display",
    )

    show_rf_levels = models.BooleanField(
        default=True,
        help_text="Show RF signal strength indicators",
    )

    show_battery_levels = models.BooleanField(
        default=True,
        help_text="Show battery percentage bars",
    )

    show_audio_levels = models.BooleanField(
        default=False,
        help_text="Show audio level indicators (VU meters)",
    )

    refresh_interval_seconds = models.IntegerField(
        default=5,
        help_text="HTMX refresh interval in seconds",
    )

    # Status
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this display is active",
    )

    last_heartbeat = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time display confirmed it was viewing content",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = DisplayWallManager()

    class Meta:
        verbose_name = "Display Wall"
        verbose_name_plural = "Display Walls"
        ordering: ClassVar[list[str]] = ["location__name", "name"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["location", "is_active"]),
            models.Index(fields=["kiosk_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.display_width_px}x{self.display_height_px}) @ {self.location}"


class WallSectionQuerySet(models.QuerySet):
    """Query helpers for wall sections."""

    def by_wall(self, *, wall_id: int) -> WallSectionQuerySet:
        """Filter by display wall."""
        return self.filter(wall_id=wall_id)

    def active(self) -> WallSectionQuerySet:
        """Get active sections only."""
        return self.filter(is_active=True)

    def with_chargers(self) -> WallSectionQuerySet:
        """Optimize: prefetch chargers."""
        return self.prefetch_related("chargers")


class WallSection(models.Model):
    """Section of a display wall assigned to show charger performers.

    A display wall can be divided into sections, each showing a different
    charger's docked devices and their performers. Sections define layout
    and positioning (grid cells, carousel, etc.).
    """

    LAYOUT_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("grid", "Grid (fixed cells)"),
        ("carousel", "Carousel (rotating)"),
        ("detail", "Detail (single large display)"),
        ("list", "List (vertical or horizontal)"),
    ]

    wall = models.ForeignKey(
        DisplayWall,
        on_delete=models.CASCADE,
        related_name="sections",
        help_text="Display wall this section belongs to",
    )

    name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Section name (e.g., 'Left Panel', 'Top Row')",
    )

    chargers = models.ManyToManyField(
        "micboard.Charger",
        related_name="wall_sections",
        blank=True,
        help_text="Chargers assigned to this section",
    )

    # Layout within wall
    layout = models.CharField(
        max_length=20,
        choices=LAYOUT_CHOICES,
        default="grid",
        help_text="Layout style for this section",
    )

    position_x_percent = models.FloatField(
        default=0,
        help_text="X position as percentage of wall width (0-100)",
    )

    position_y_percent = models.FloatField(
        default=0,
        help_text="Y position as percentage of wall height (0-100)",
    )

    width_percent = models.FloatField(
        default=100,
        help_text="Section width as percentage of wall width (0-100)",
    )

    height_percent = models.FloatField(
        default=100,
        help_text="Section height as percentage of wall height (0-100)",
    )

    # Display options
    columns = models.PositiveIntegerField(
        default=3,
        help_text="Number of columns if using grid layout",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this section is active",
    )

    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Display order for carousel or rotation",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Wall Section"
        verbose_name_plural = "Wall Sections"
        ordering: ClassVar[list[str]] = ["wall__location__name", "wall__name", "display_order"]
        unique_together: ClassVar[list[list[str]]] = [["wall", "name"]]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["wall", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.wall.name} - {self.name or 'Default Section'}"
