"""Wireless unit session and sample models for telemetry tracking."""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.utils import timezone


class WirelessUnitSession(models.Model):
    """Represents a period where a wireless unit is considered active."""

    wireless_unit = models.ForeignKey(
        "micboard.WirelessUnit",
        on_delete=models.CASCADE,
        related_name="sessions",
        help_text="The wireless unit this session belongs to",
    )
    started_at = models.DateTimeField(help_text="When this session started")
    last_seen = models.DateTimeField(help_text="Last time data was seen for this unit")
    ended_at = models.DateTimeField(null=True, blank=True, help_text="When this session ended")
    is_active = models.BooleanField(
        default=True, help_text="Whether the session is currently active"
    )
    last_status = models.CharField(max_length=50, blank=True, help_text="Last known unit status")
    sample_count = models.PositiveIntegerField(
        default=0, help_text="Number of samples recorded in this session"
    )

    class Meta:
        verbose_name = "Wireless Unit Session"
        verbose_name_plural = "Wireless Unit Sessions"
        ordering: ClassVar[list[str]] = ["-started_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["wireless_unit", "is_active"]),
            models.Index(fields=["started_at"]),
        ]

    def __str__(self) -> str:
        state = "active" if self.is_active else "ended"
        return f"Session {state} for {self.wireless_unit} from {self.started_at}"


class WirelessUnitSample(models.Model):
    """A single data point captured during a wireless unit session."""

    session = models.ForeignKey(
        WirelessUnitSession,
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
        verbose_name = "Wireless Unit Sample"
        verbose_name_plural = "Wireless Unit Samples"
        ordering: ClassVar[list[str]] = ["-timestamp"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["timestamp"]),
        ]

    def __str__(self) -> str:
        return f"Sample @ {self.timestamp} for {self.session.wireless_unit}"


# Legacy aliases for backward compatibility during migration
TransmitterSession = WirelessUnitSession
TransmitterSample = WirelessUnitSample
