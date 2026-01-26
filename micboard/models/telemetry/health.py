"""API health monitoring and logging models."""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils import timezone


class APIHealthLog(models.Model):
    """Logs API availability and health status for manufacturers."""

    manufacturer = models.ForeignKey(
        "micboard.Manufacturer",
        on_delete=models.CASCADE,
        help_text="The manufacturer this health log relates to",
    )
    timestamp = models.DateTimeField(
        default=timezone.now, help_text="When the health check was performed"
    )
    status = models.CharField(max_length=20, help_text="Health status (e.g., healthy, unhealthy)")
    response_time = models.FloatField(
        null=True, blank=True, help_text="API response time in seconds"
    )
    error_message = models.TextField(blank=True, help_text="Error message if unhealthy")
    details = models.JSONField(default=dict, help_text="Additional health check details")

    class Meta:
        verbose_name = "API Health Log"
        verbose_name_plural = "API Health Logs"
        ordering: ClassVar[list[str]] = ["-timestamp"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["manufacturer", "timestamp"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self) -> str:
        return f"{self.manufacturer.name} API {self.status} @ {self.timestamp}"
