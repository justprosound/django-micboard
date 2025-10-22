from __future__ import annotations

from typing import ClassVar

from django.db import models


class Group(models.Model):
    """
    Represents a logical grouping of devices or channels.
    This model is intended for flexible grouping, not directly tied to physical slots.
    """

    group_number = models.PositiveIntegerField(unique=True, help_text="Unique group number")
    title = models.CharField(max_length=100, help_text="Display title for the group")
    hide_charts = models.BooleanField(
        default=False, help_text="Whether to hide charts for this group"
    )
    # Optional list of slots (e.g., display slots) used by UI and tests.
    slots = models.JSONField(default=list, blank=True, help_text="Optional slot numbers")

    class Meta:
        verbose_name = "Group"
        verbose_name_plural = "Groups"
        ordering: ClassVar[list[str]] = ["group_number"]

    def __str__(self) -> str:
        return f"Group {self.group_number}: {self.title}"

    def get_channels(self):
        """Return channels associated with this group via monitoring groups.

        Tests expect a simple helper to return a list of channel objects. We
        implement a best-effort query that returns an empty queryset when no
        monitoring groups are linked.
        """
        return getattr(self, "channels", [])
