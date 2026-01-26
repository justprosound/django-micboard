# file: micboard/models/monitoring/assignment.py
from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from django.contrib.auth import get_user_model
from django.db import models

from micboard.models.base_managers import TenantOptimizedManager, TenantOptimizedQuerySet

User = get_user_model()


class DeviceAssignmentQuerySet(TenantOptimizedQuerySet):
    """Query helpers for active assignments with tenant awareness."""

    def active(self) -> DeviceAssignmentQuerySet:
        return self.filter(is_active=True)

    def for_user(self, *, user) -> DeviceAssignmentQuerySet:
        return self.active().filter(user=user)

    def with_channel(self) -> DeviceAssignmentQuerySet:
        return self.select_related(
            "channel",
            "channel__chassis",
            "channel__chassis__manufacturer",
        )

    def needing_alerts(self, *, after: datetime | None = None) -> DeviceAssignmentQuerySet:
        qs = self.active().filter(alert_on_device_offline=True)
        if after:
            qs = qs.filter(updated_at__gte=after)
        return qs


class DeviceAssignmentManager(TenantOptimizedManager):
    """Manager exposing typed helpers for services and views."""

    def get_queryset(self) -> DeviceAssignmentQuerySet:
        return DeviceAssignmentQuerySet(self.model, using=self._db)

    def active(self) -> DeviceAssignmentQuerySet:
        return self.get_queryset().active()

    def for_user(self, *, user) -> DeviceAssignmentQuerySet:
        return self.get_queryset().for_user(user=user)

    def needing_alerts(self, *, after: datetime | None = None) -> DeviceAssignmentQuerySet:
        return self.get_queryset().needing_alerts(after=after)


class DeviceAssignment(models.Model):
    """Individual device/channel assignments to users.
    Allows fine-grained control over who monitors what.
    """

    PRIORITY_CHOICES: ClassVar[list[tuple[str, str]]] = [
        ("low", "Low"),
        ("normal", "Normal"),
        ("high", "High"),
        ("critical", "Critical"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="device_assignments",
        help_text="User assigned to monitor this device",
    )

    channel = models.ForeignKey(
        "micboard.RFChannel",
        on_delete=models.CASCADE,
        related_name="assignments",
        help_text="Channel being monitored",
    )
    location = models.ForeignKey(
        "micboard.Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="device_assignments",
        help_text="Physical location of this device",
    )
    monitoring_group = models.ForeignKey(
        "micboard.MonitoringGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="device_assignments",
        help_text="Optional monitoring group this assignment belongs to",
    )

    # Assignment metadata
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default="normal",
        help_text="Priority level for this assignment",
    )
    notes = models.TextField(
        blank=True, help_text="Notes about this assignment (e.g., 'Lead vocalist mic')"
    )
    is_active = models.BooleanField(
        default=True, help_text="Whether this assignment is currently active"
    )

    # Alert preferences for this specific assignment
    alert_on_battery_low = models.BooleanField(default=True, help_text="Alert when battery is low")
    alert_on_signal_loss = models.BooleanField(
        default=True, help_text="Alert when RF signal is lost"
    )
    alert_on_audio_low = models.BooleanField(
        default=False, help_text="Alert when audio level is too low"
    )
    alert_on_device_offline = models.BooleanField(
        default=True, help_text="Alert when device goes offline"
    )

    # Timestamps
    assigned_at = models.DateTimeField(
        auto_now_add=True, help_text="When this assignment was created"
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignments_created",
        help_text="User who created this assignment",
    )
    updated_at = models.DateTimeField(auto_now=True, help_text="Last update timestamp")

    objects = DeviceAssignmentManager()

    class Meta:
        verbose_name = "Device Assignment"
        verbose_name_plural = "Device Assignments"
        ordering: ClassVar[list[str]] = [
            "-priority",
            "channel",
        ]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["channel", "is_active"]),
            models.Index(fields=["priority", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.user.username} -> {self.channel} ({self.priority})"

    def get_alert_preferences(self) -> dict[str, bool]:
        """Get alert preferences for this assignment."""
        return {
            "battery_low": self.alert_on_battery_low,
            "signal_loss": self.alert_on_signal_loss,
            "audio_low": self.alert_on_audio_low,
            "device_offline": self.alert_on_device_offline,
        }


# Alias for backwards compatibility if needed, though strictly we should avoid legacy
# Assignment = DeviceAssignment
