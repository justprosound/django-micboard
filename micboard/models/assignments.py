"""Assignment and alert models for the micboard app."""
from __future__ import annotations

from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class DeviceAssignment(models.Model):
    """
    Individual device/channel assignments to users.
    Allows fine-grained control over who monitors what.
    """

    PRIORITY_CHOICES = [
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
    # Changed from 'Device' to 'Channel'
    channel = models.ForeignKey(
        "Channel",  # Reference the new Channel model
        on_delete=models.CASCADE,
        related_name="assignments",
        help_text="Channel being monitored",
    )
    location = models.ForeignKey(
        "Location",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="device_assignments",
        help_text="Physical location of this device",
    )
    monitoring_group = models.ForeignKey(
        "MonitoringGroup",
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

    class Meta:
        verbose_name = "Device Assignment"
        verbose_name_plural = "Device Assignments"
        ordering = ["-priority", "channel"]  # Changed from 'device' to 'channel'
        unique_together = [["user", "channel"]]  # One assignment per user per channel
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["channel", "is_active"]),  # Changed from 'device' to 'channel'
            models.Index(fields=["priority", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.user.username} -> {self.channel} ({self.priority})"  # Changed from 'device' to 'channel'

    def get_alert_preferences(self) -> dict[str, bool]:
        """Get alert preferences for this assignment"""
        return {
            "battery_low": self.alert_on_battery_low,
            "signal_loss": self.alert_on_signal_loss,
            "audio_low": self.alert_on_audio_low,
            "device_offline": self.alert_on_device_offline,
        }


class UserAlertPreference(models.Model):
    """
    Global alert preferences per user.
    Device-specific preferences override these defaults.
    """

    NOTIFICATION_METHODS = [
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
    default_alert_device_offline = models.BooleanField(
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
        """Check if current time is within quiet hours"""
        if not self.quiet_hours_enabled:
            return False

        now = current_time or timezone.now().time()

        if self.quiet_hours_start and self.quiet_hours_end:
            if self.quiet_hours_start <= self.quiet_hours_end:
                # Same day range
                return self.quiet_hours_start <= now <= self.quiet_hours_end
            # Overnight range
            return now >= self.quiet_hours_start or now <= self.quiet_hours_end

        return False


class Alert(models.Model):
    """
    Stores alert history for auditing and tracking.
    """

    ALERT_TYPES = [
        ("battery_low", "Battery Low"),
        ("battery_critical", "Battery Critical"),
        ("signal_loss", "Signal Loss"),
        ("audio_low", "Audio Low"),
        ("device_offline", "Device Offline"),
        ("device_online", "Device Online"),
    ]

    ALERT_STATUS = [
        ("pending", "Pending"),
        ("sent", "Sent"),
        ("acknowledged", "Acknowledged"),
        ("resolved", "Resolved"),
        ("failed", "Failed"),
    ]

    # Changed from 'Device' to 'Channel'
    channel = models.ForeignKey(
        "Channel",  # Reference the new Channel model
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
        DeviceAssignment,
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
    channel_data = models.JSONField(  # Renamed from device_data to channel_data for clarity
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
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["channel", "alert_type", "status"]
            ),  # Changed from 'device' to 'channel'
            models.Index(fields=["user", "status", "-created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.alert_type} - {self.channel} ({self.status})"  # Changed from 'device' to 'channel'

    def acknowledge(self, user: User) -> None:
        """Mark alert as acknowledged"""
        _ = user  # Mark as intentionally unused for now
        self.status = "acknowledged"
        self.acknowledged_at = timezone.now()
        self.save()

    def resolve(self) -> None:
        """Mark alert as resolved"""
        self.status = "resolved"
        self.resolved_at = timezone.now()
        self.save()

    @property
    def is_overdue(self) -> bool:
        """Check if alert is overdue for response"""
        if self.status in ["acknowledged", "resolved"]:
            return False

        # Consider overdue after 30 minutes
        return (timezone.now() - self.created_at) > timedelta(minutes=30)
