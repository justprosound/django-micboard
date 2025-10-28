from __future__ import annotations

from datetime import timedelta
from typing import ClassVar

from django.db import models
from django.utils import timezone


class Transmitter(models.Model):
    # Sentinel values
    UNKNOWN_BYTE_VALUE: ClassVar = 255
    """Represents the wireless transmitter data associated with a Channel."""

    channel = models.OneToOneField(
        "micboard.Channel",
        on_delete=models.CASCADE,
        related_name="transmitter",
        help_text="The channel this transmitter belongs to",
    )
    slot = models.PositiveIntegerField(
        unique=True, help_text="Unique slot number for this channel/transmitter combination"
    )
    # Real-time data from API
    battery = models.PositiveIntegerField(
        default=UNKNOWN_BYTE_VALUE, help_text="Battery level (0-255, 255=unknown)"
    )
    battery_charge = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Battery charge percentage (0-100, optional field from newer devices)",
    )
    audio_level = models.IntegerField(default=0, help_text="Audio level in dB")
    rf_level = models.IntegerField(default=0, help_text="RF signal level")
    frequency = models.CharField(max_length=20, blank=True, help_text="Operating frequency")
    antenna = models.CharField(max_length=10, blank=True, help_text="Antenna information")
    tx_offset = models.IntegerField(default=UNKNOWN_BYTE_VALUE, help_text="Transmitter offset")
    quality = models.PositiveIntegerField(
        default=UNKNOWN_BYTE_VALUE, help_text="Signal quality (0-255)"
    )
    runtime = models.CharField(max_length=20, blank=True, help_text="Runtime information")
    status = models.CharField(max_length=50, blank=True, help_text="Transmitter status")
    name = models.CharField(max_length=100, blank=True, help_text="Transmitter name")
    name_raw = models.CharField(max_length=100, blank=True, help_text="Raw transmitter name")
    charging_status = models.BooleanField(default=False, help_text="Whether the transmitter is currently charging")
    updated_at = models.DateTimeField(auto_now=True, help_text="Last update timestamp")

    class Meta:
        verbose_name = "Transmitter"
        verbose_name_plural = "Transmitters"
        ordering: ClassVar[list[str]] = ["channel__receiver__name", "channel__channel_number"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["channel", "slot"]),
        ]

    def __str__(self) -> str:
        return f"Transmitter for {self.channel} (Slot {self.slot})"

    @property
    def battery_percentage(self) -> int | None:
        """Get battery level as percentage"""
        if self.battery == self.UNKNOWN_BYTE_VALUE:
            return None
        return min(100, max(0, self.battery * 100 // self.UNKNOWN_BYTE_VALUE))  # type: ignore

    @property
    def battery_health(self) -> str:
        """Get battery health status"""
        pct = self.battery_percentage
        if pct is None:
            return "unknown"
        if pct > 50:
            return "good"
        if pct > 25:
            return "fair"
        if pct > 10:
            return "low"
        return "critical"

    @property
    def is_active(self) -> bool:
        """Check if transmitter is currently active (recently updated)"""
        if not self.updated_at:
            return False
        time_since = timezone.now() - self.updated_at
        return time_since < timedelta(minutes=5)  # type: ignore

    def get_signal_quality(self) -> str:
        """Get signal quality as text"""
        if self.quality == self.UNKNOWN_BYTE_VALUE:
            return "unknown"
        if self.quality > 200:
            return "excellent"
        if self.quality > 150:
            return "good"
        if self.quality > 100:
            return "fair"
        return "poor"
