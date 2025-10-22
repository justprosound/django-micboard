from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils import timezone


class APIHealthLog(models.Model):
    """Logs API availability and health status for manufacturers."""

    manufacturer = models.ForeignKey(
        "Manufacturer",
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


class TransmitterSession(models.Model):
    """Represents a period where a transmitter is considered active.

    A session starts when we first receive data for a transmitter and ends when
    no data has been received for a configured inactivity threshold.
    """

    transmitter = models.ForeignKey(
        "Transmitter",
        on_delete=models.CASCADE,
        related_name="sessions",
        help_text="The transmitter this session belongs to",
    )
    started_at = models.DateTimeField(help_text="When this session started")
    last_seen = models.DateTimeField(help_text="Last time data was seen for this transmitter")
    ended_at = models.DateTimeField(null=True, blank=True, help_text="When this session ended")
    is_active = models.BooleanField(
        default=True, help_text="Whether the session is currently active"
    )
    last_status = models.CharField(
        max_length=50, blank=True, help_text="Last known transmitter status"
    )
    sample_count = models.PositiveIntegerField(
        default=0, help_text="Number of samples recorded in this session"
    )

    class Meta:
        verbose_name = "Transmitter Session"
        verbose_name_plural = "Transmitter Sessions"
        ordering: ClassVar[list[str]] = ["-started_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["transmitter", "is_active"]),
            models.Index(fields=["started_at"]),
        ]

    def __str__(self) -> str:
        state = "active" if self.is_active else "ended"
        return f"Session {state} for {self.transmitter} from {self.started_at}"


class TransmitterSample(models.Model):
    """A single data point captured during a transmitter session."""

    session = models.ForeignKey(
        TransmitterSession,
        on_delete=models.CASCADE,
        related_name="samples",
        help_text="The session this sample belongs to",
    )
    timestamp = models.DateTimeField(default=timezone.now, help_text="When the sample was recorded")
    battery = models.PositiveIntegerField(null=True, blank=True)
    battery_charge = models.PositiveIntegerField(null=True, blank=True)
    audio_level = models.IntegerField(null=True, blank=True)
    rf_level = models.IntegerField(null=True, blank=True)
    quality = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=50, blank=True)
    frequency = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = "Transmitter Sample"
        verbose_name_plural = "Transmitter Samples"
        ordering: ClassVar[list[str]] = ["-timestamp"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["timestamp"]),
        ]

    def __str__(self) -> str:
        return f"Sample @ {self.timestamp} for {self.session.transmitter}"
