# file: micboard/models/monitoring/alert.py
from __future__ import annotations

from datetime import time, timedelta
from typing import ClassVar

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class UserAlertPreference(models.Model):
    """Global alert preferences per user.

    Device-specific preferences override these defaults.
    """

    NOTIFICATION_METHODS: ClassVar[list[tuple[str, str]]] = [
        ("email", "Email"),
        ("websocket", "WebSocket (Real-time)"),
        ("both", "Email + WebSocket"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="alert_preferences",
        help_text="User these preferences belong to",
    )

    # Notification delivery
    notification_method = models.CharField(
        max_length=20,
        choices=NOTIFICATION_METHODS,
        default="both",
        help_text="How alerts should be delivered",
    )
    email_address = models.EmailField(
        blank=True, help_text="Override user's default email for alerts"
    )

    # Global alert settings (defaults)
    default_alert_battery_low = models.BooleanField(
        default=True, help_text="Default alert setting for battery low"
    )
    default_alert_signal_loss = models.BooleanField(
        default=True, help_text="Default alert setting for signal loss"
    )
    default_alert_audio_low = models.BooleanField(
        default=False, help_text="Default alert setting for audio low"
    )
    default_alert_hardware_offline = models.BooleanField(
        default=True, help_text="Default alert setting for device offline"
    )

    # Battery thresholds
    battery_low_threshold = models.PositiveIntegerField(
        default=20, help_text="Alert when battery percentage drops below this value"
    )
    battery_critical_threshold = models.PositiveIntegerField(
        default=10, help_text="Critical alert threshold"
    )

    # Quiet hours
    quiet_hours_enabled = models.BooleanField(
        default=False, help_text="Enable quiet hours (no alerts during specified times)"
    )
    quiet_hours_start = models.TimeField(
        null=True, blank=True, help_text="Start of quiet hours (e.g., 22:00)"
    )
    quiet_hours_end = models.TimeField(
        null=True, blank=True, help_text="End of quiet hours (e.g., 08:00)"
    )

    # Alert rate limiting
    min_alert_interval = models.PositiveIntegerField(
        default=5, help_text="Minimum minutes between alerts for the same device"
    )

    created_at = models.DateTimeField(
        auto_now_add=True, help_text="When these preferences were created"
    )
    updated_at = models.DateTimeField(auto_now=True, help_text="Last update timestamp")

    class Meta:
        verbose_name = "User Alert Preference"
        verbose_name_plural = "User Alert Preferences"

    def __str__(self) -> str:
        return f"Alert preferences for {self.user.username}"

    def is_quiet_hours(self, current_time: time | None = None) -> bool:
        """Check if current time is within quiet hours."""
        if not self.quiet_hours_enabled:
            return False

        now = current_time or timezone.now().time()

        if self.quiet_hours_start and self.quiet_hours_end:
            if self.quiet_hours_start <= self.quiet_hours_end:
                # Same day range
                return self.quiet_hours_start <= now <= self.quiet_hours_end  # type: ignore
            # Overnight range
            return now >= self.quiet_hours_start or now <= self.quiet_hours_end  # type: ignore

        return False


class Alert(models.Model):
    """Stores alert history for auditing and tracking."""

    ALERT_TYPES: ClassVar[list[tuple[str, str]]] = [
        ("battery_low", "Battery Low"),
        ("battery_critical", "Battery Critical"),
        ("signal_loss", "Signal Loss"),
        ("audio_low", "Audio Low"),
        ("hardware_offline", "Device Offline"),
        ("hardware_online", "Device Online"),
    ]

    ALERT_STATUS: ClassVar[list[tuple[str, str]]] = [
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("acknowledged", "Acknowledged"),
        ("resolved", "Resolved"),
        ("failed", "Failed"),
    ]

    channel = models.ForeignKey(
        "micboard.RFChannel",
        on_delete=models.CASCADE,
        related_name="alerts",
        help_text="Channel that triggered the alert",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="alerts",
        help_text="User who should receive the alert",
    )
    assignment = models.ForeignKey(
        "micboard.PerformerAssignment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
        help_text="Specific assignment this alert relates to",
    )

    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES, help_text="Type of alert")
    status = models.CharField(
        max_length=20,
        choices=ALERT_STATUS,
        default="pending",
        help_text="Current status of the alert",
    )
    message = models.TextField(help_text="Alert message text")

    # Alert context data
    channel_data = models.JSONField(
        null=True, blank=True, help_text="Snapshot of channel state when alert was triggered"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, help_text="When the alert was created")
    sent_at = models.DateTimeField(null=True, blank=True, help_text="When the alert was sent")
    acknowledged_at = models.DateTimeField(
        null=True, blank=True, help_text="When the alert was acknowledged"
    )
    resolved_at = models.DateTimeField(
        null=True, blank=True, help_text="When the alert was resolved"
    )

    class Meta:
        verbose_name = "Alert"
        verbose_name_plural = "Alerts"
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["channel", "alert_type", "status"]),
            models.Index(fields=["user", "status", "-created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.alert_type} - {self.channel} ({self.status})"

    @property
    def is_overdue(self) -> bool:
        """Check if alert is overdue for response."""
        if self.status in ["acknowledged", "resolved"]:
            return False

        # Consider overdue after 30 minutes
        return (timezone.now() - self.created_at) > timedelta(minutes=30)  # type: ignore

    @property
    def severity(self) -> str:
        """Return severity level based on alert type."""
        if self.alert_type in ["battery_critical", "hardware_offline"]:
            return "High"
        if self.alert_type in ["signal_loss"]:
            return "Medium"
        return "Low"
