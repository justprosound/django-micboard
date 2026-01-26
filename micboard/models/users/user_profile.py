"""User profile extensions for micboard-specific user personas.

Adds Performer-specific metadata (photo, title, role) to support
human-centric monitoring and the Charger Dashboard.
"""

from __future__ import annotations

from typing import ClassVar

from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class UserProfile(models.Model):
    """Profile extending standard User with Performer and Technician metadata."""

    USER_TYPES: ClassVar[list[tuple[str, str]]] = [
        ("performer", "Performer/Talent"),
        ("technician", "Facility Technician"),
        ("admin", "Administrator"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    user_type = models.CharField(
        max_length=20,
        choices=USER_TYPES,
        default="performer",
        help_text="Primary role of this user in the system",
    )

    # Performer Metadata
    title = models.CharField(
        max_length=100,
        blank=True,
        help_text="Job title or character name (e.g., 'Lead Vocalist', 'News Anchor')",
    )
    role_description = models.TextField(
        blank=True,
        help_text="Detailed description of the user's responsibilities or equipment requirements",
    )
    photo = models.ImageField(
        upload_to="performer_photos/",
        null=True,
        blank=True,
        help_text="Headshot for visual identification on dashboards",
    )

    display_width_px = models.PositiveIntegerField(
        default=1920,
        help_text="Physical display width in pixels for charger dashboard scaling",
    )

    # Activity tracking
    last_active_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self) -> str:
        return f"{self.user.get_full_name() or self.user.username} ({self.get_user_type_display()})"
