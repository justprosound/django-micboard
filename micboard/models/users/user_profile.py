"""User profile extensions for technicians and administrators.

Extends standard User with role and monitoring preferences.
Performers (talent/device users) are represented by the Performer model.
"""

from __future__ import annotations

from typing import ClassVar

from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class UserProfile(models.Model):
    """Profile extending standard User for technicians and administrators.

    Technicians and admins monitor and manage performer assignments and
    wireless devices within their assigned MonitoringGroups.
    """

    USER_TYPES: ClassVar[list[tuple[str, str]]] = [
        ("technician", "Facility Technician"),
        ("admin", "Administrator"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
        help_text="Django user account",
    )
    user_type = models.CharField(
        max_length=20,
        choices=USER_TYPES,
        default="technician",
        help_text="Role of this user (technician or admin)",
    )

    # Technician/Admin metadata
    title = models.CharField(
        max_length=100,
        blank=True,
        help_text="Job title (e.g., 'Audio Tech', 'RF Manager')",
    )
    role_description = models.TextField(
        blank=True,
        help_text="Description of responsibilities and permissions",
    )

    # Charger Dashboard scaling
    display_width_px = models.PositiveIntegerField(
        default=1920,
        help_text="Physical display width in pixels for dashboard scaling",
    )

    # Activity tracking
    last_active_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last login or activity time",
    )

    # Timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this profile was created",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last update timestamp",
    )

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"

    def __str__(self) -> str:
        return f"{self.user.get_full_name() or self.user.username} ({self.get_user_type_display()})"

    def get_monitoring_groups(self):
        """Get all monitoring groups this user is a member of."""
        return self.user.monitoring_groups.filter(is_active=True)

    def get_accessible_performers(self):
        """Get all performers accessible through user's monitoring groups."""
        from micboard.models import Performer, PerformerAssignment

        performer_ids = PerformerAssignment.objects.filter(
            monitoring_group__in=self.get_monitoring_groups(), is_active=True
        ).values_list("performer_id", flat=True)

        return Performer.objects.filter(id__in=performer_ids, is_active=True)

    def get_accessible_devices(self):
        """Get all wireless units accessible through user's monitoring groups."""
        from micboard.models import PerformerAssignment, WirelessUnit

        unit_ids = PerformerAssignment.objects.filter(
            monitoring_group__in=self.get_monitoring_groups(), is_active=True
        ).values_list("wireless_unit_id", flat=True)

        return WirelessUnit.objects.filter(id__in=unit_ids, is_active=True)
