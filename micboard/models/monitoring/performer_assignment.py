"""Performer assignment model linking performers to wireless units."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from django.contrib.auth import get_user_model
from django.db import models

from micboard.models.base_managers import TenantOptimizedManager, TenantOptimizedQuerySet

User = get_user_model()


class PerformerAssignmentQuerySet(TenantOptimizedQuerySet):
    """Query helpers for performer assignments with tenant awareness."""

    def active(self) -> PerformerAssignmentQuerySet:
        """Get all active assignments."""
        return self.filter(is_active=True)

    def by_monitoring_group(self, *, group) -> PerformerAssignmentQuerySet:
        """Filter by monitoring group that manages this assignment."""
        return self.filter(monitoring_group=group)

    def with_performer_and_unit(self) -> PerformerAssignmentQuerySet:
        """Optimize: select related performer and wireless unit."""
        return self.select_related(
            "performer",
            "wireless_unit",
            "wireless_unit__base_chassis",
            "wireless_unit__base_chassis__location",
        )

    def needing_alerts(self, *, after: datetime | None = None) -> PerformerAssignmentQuerySet:
        """Filter assignments with alerts enabled."""
        qs = self.active().filter(
            models.Q(alert_on_battery_low=True)
            | models.Q(alert_on_signal_loss=True)
            | models.Q(alert_on_hardware_offline=True)
        )
        if after:
            qs = qs.filter(updated_at__gte=after)
        return qs


class PerformerAssignmentManager(TenantOptimizedManager):
    """Manager for performer assignments."""

    def get_queryset(self) -> PerformerAssignmentQuerySet:
        return PerformerAssignmentQuerySet(self.model, using=self._db)

    def active(self) -> PerformerAssignmentQuerySet:
        return self.get_queryset().active()

    def by_monitoring_group(self, *, group) -> PerformerAssignmentQuerySet:
        return self.get_queryset().by_monitoring_group(group=group)


class PerformerAssignment(models.Model):
    """Assignment of a performer to a wireless unit.

    Represents the link between a performer (talent) and the wireless device
    they will use. Allows multiple performers to share units across different
    events/sessions, and tracks metadata about each assignment.
    """

    PRIORITY_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("low", "Low"),
        ("normal", "Normal"),
        ("high", "High"),
        ("critical", "Critical"),
    ]

    # Core assignment
    performer = models.ForeignKey(
        "micboard.Performer",
        on_delete=models.CASCADE,
        related_name="assignments",
        help_text="Performer assigned to this unit",
    )
    wireless_unit = models.ForeignKey(
        "micboard.WirelessUnit",
        on_delete=models.CASCADE,
        related_name="performer_assignments",
        help_text="Wireless unit assigned to performer",
    )

    # Organizational context
    monitoring_group = models.ForeignKey(
        "micboard.MonitoringGroup",
        on_delete=models.CASCADE,
        related_name="performer_assignments",
        help_text="Monitoring group managing this assignment",
    )

    # Assignment metadata
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default="normal",
        help_text="Priority level for monitoring this performer's device",
    )
    notes = models.TextField(
        blank=True,
        help_text="Notes about this assignment (equipment config, special requirements, etc)",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this assignment is currently active",
    )

    # Performer-specific alert preferences
    alert_on_battery_low = models.BooleanField(
        default=True,
        help_text="Alert when battery is low",
    )
    alert_on_signal_loss = models.BooleanField(
        default=True,
        help_text="Alert when RF signal is lost",
    )
    alert_on_audio_low = models.BooleanField(
        default=False,
        help_text="Alert when audio level is too low",
    )
    alert_on_hardware_offline = models.BooleanField(
        default=True,
        help_text="Alert when device goes offline",
    )

    # Audit trail
    assigned_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this assignment was created",
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="performer_assignments_created",
        help_text="Technician/admin who created this assignment",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last update timestamp",
    )

    objects = PerformerAssignmentManager()

    class Meta:
        verbose_name = "Performer Assignment"
        verbose_name_plural = "Performer Assignments"
        unique_together: ClassVar[list[list[str]]] = [["performer", "wireless_unit"]]
        ordering: ClassVar[list[str]] = ["-priority", "performer", "wireless_unit"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["performer", "is_active"]),
            models.Index(fields=["wireless_unit", "is_active"]),
            models.Index(fields=["monitoring_group", "is_active"]),
            models.Index(fields=["priority", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.performer.name} -> {self.wireless_unit.name} ({self.priority})"

    def get_alert_preferences(self) -> dict[str, bool]:
        """Get alert preferences for this assignment (delegates to service)."""
        from micboard.services.monitoring.performer_assignment_service import get_alert_preferences

        return get_alert_preferences(self)
