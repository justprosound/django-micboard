# file: micboard/models/monitoring/group.py
"""Group models for logical organization of devices, channels, and users.

Contains:
- Group: Legacy/Simple UI grouping.
- MonitoringGroup: Robust team/permission grouping.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class Group(models.Model):
    """Represents a logical grouping of devices or channels.
    This model is intended for flexible grouping, not directly tied to physical slots.
    Legacy model used for simple UI organization.
    """

    group_number = models.PositiveIntegerField(unique=True, help_text="Unique group number")
    title = models.CharField(max_length=100, help_text="Display title for the group")
    hide_charts = models.BooleanField(
        default=False, help_text="Whether to hide charts for this group"
    )
    # Optional list of slots (e.g., display slots) used by UI and tests.
    slots = models.JSONField(default=list, blank=True, help_text="Optional slot numbers")

    members = models.ManyToManyField(
        "micboard.WirelessUnit",
        related_name="legacy_groups",
        blank=True,
        help_text="Wireless units in this group",
    )

    class Meta:
        verbose_name = "Group"
        verbose_name_plural = "Groups"
        ordering: ClassVar[list[str]] = ["group_number"]

    def __str__(self) -> str:
        return f"Group {self.group_number}: {self.title}"


class MonitoringGroup(models.Model):
    """Represents a group of users who monitor specific devices together.
    Useful for organizing teams (e.g., "Theater Tech Team", "Conference Room A Staff").
    """

    name = models.CharField(
        max_length=100, unique=True, help_text="Unique name for the monitoring group"
    )
    description = models.TextField(blank=True, help_text="Description of the monitoring group")
    users = models.ManyToManyField(
        "auth.User",
        related_name="monitoring_groups",
        blank=True,
        help_text="Users who are part of this monitoring group",
    )
    locations = models.ManyToManyField(
        "micboard.Location",
        through="MonitoringGroupLocation",
        related_name="monitoring_groups",
        blank=True,
        help_text="Locations assigned to this monitoring group",
    )
    channels = models.ManyToManyField(
        "micboard.RFChannel",
        related_name="monitoring_groups",
        blank=True,
        help_text="Channels assigned to this monitoring group",
    )
    is_active = models.BooleanField(
        default=True, help_text="Whether this monitoring group is active"
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="When this group was created")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last update timestamp")

    class Meta:
        verbose_name = "Monitoring Group"
        verbose_name_plural = "Monitoring Groups"
        ordering: ClassVar[list[str]] = ["name"]

    def __str__(self) -> str:
        return str(self.name)

    def get_active_users(self):
        """Get all active users in this group."""
        return self.users.filter(is_active=True)

    def get_active_channels(self):
        """Get all active RF channels in this group (RFChannel model)."""
        return self.channels.filter(enabled=True)


class MonitoringGroupLocation(models.Model):
    """Intermediary model for MonitoringGroup and Location, specifying access scope."""

    monitoring_group = models.ForeignKey(MonitoringGroup, on_delete=models.CASCADE)
    location = models.ForeignKey("micboard.Location", on_delete=models.CASCADE)
    include_all_rooms = models.BooleanField(
        default=False,
        help_text=(
            "If true, this group has access to all rooms within the specified "
            "building of the location."
        ),
    )

    class Meta:
        unique_together: ClassVar[list[list[str]]] = [["monitoring_group", "location"]]
        verbose_name = "Monitoring Group Location"
        verbose_name_plural = "Monitoring Group Locations"

    def __str__(self) -> str:
        return f"{self.monitoring_group.name} - {self.location.full_address}"
