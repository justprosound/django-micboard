"""
Models for tracking real-time connections and subscriptions.
"""

from __future__ import annotations

from datetime import timedelta
from typing import ClassVar

from django.db import models
from django.utils import timezone


class RealTimeConnection(models.Model):
    """
    Tracks real-time connections (SSE/WebSocket) for devices.

    This model maintains the status of active real-time subscriptions
    and provides monitoring capabilities.
    """

    CONNECTION_TYPES: ClassVar[list[tuple[str, str]]] = [
        ("sse", "Server-Sent Events"),
        ("websocket", "WebSocket"),
    ]

    CONNECTION_STATUS: ClassVar[list[tuple[str, str]]] = [
        ("connecting", "Connecting"),
        ("connected", "Connected"),
        ("disconnected", "Disconnected"),
        ("error", "Error"),
        ("stopped", "Stopped"),
    ]

    # Device reference
    receiver = models.OneToOneField(
        "Receiver",
        on_delete=models.CASCADE,
        related_name="realtime_connection",
        help_text="The receiver this connection is for",
    )

    # Connection details
    connection_type = models.CharField(
        max_length=20,
        choices=CONNECTION_TYPES,
        help_text="Type of real-time connection",
    )
    status = models.CharField(
        max_length=20,
        choices=CONNECTION_STATUS,
        default="disconnected",
        help_text="Current connection status",
    )

    # Connection metadata
    connected_at = models.DateTimeField(
        null=True, blank=True, help_text="When the connection was established"
    )
    last_message_at = models.DateTimeField(
        null=True, blank=True, help_text="When the last message was received"
    )
    disconnected_at = models.DateTimeField(
        null=True, blank=True, help_text="When the connection was lost"
    )

    # Error tracking
    error_message = models.TextField(
        blank=True, help_text="Last error message if connection failed"
    )
    error_count = models.PositiveIntegerField(
        default=0, help_text="Number of consecutive connection errors"
    )
    last_error_at = models.DateTimeField(
        null=True, blank=True, help_text="When the last error occurred"
    )

    # Connection configuration
    reconnect_attempts = models.PositiveIntegerField(
        default=0, help_text="Number of reconnection attempts"
    )
    max_reconnect_attempts = models.PositiveIntegerField(
        default=5, help_text="Maximum number of reconnection attempts before giving up"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Real-Time Connection"
        verbose_name_plural = "Real-Time Connections"
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["status", "connection_type"]),
            models.Index(fields=["receiver", "status"]),
            models.Index(fields=["last_message_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.connection_type} - {self.receiver} ({self.status})"

    def mark_connected(self) -> None:
        """Mark connection as successfully established."""
        self.status = "connected"
        self.connected_at = timezone.now()
        self.last_message_at = timezone.now()
        self.disconnected_at = None
        self.error_count = 0
        self.error_message = ""
        self.reconnect_attempts = 0
        self.save()

    def mark_disconnected(self, error_message: str = "") -> None:
        """Mark connection as disconnected."""
        self.status = "disconnected"
        self.disconnected_at = timezone.now()
        if error_message:
            self.error_message = error_message
            self.error_count += 1
            self.last_error_at = timezone.now()
        self.save()

    def mark_error(self, error_message: str) -> None:
        """Mark connection as having an error."""
        self.status = "error"
        self.error_message = error_message
        self.error_count += 1
        self.last_error_at = timezone.now()
        self.save()

    def mark_connecting(self) -> None:
        """Mark connection as attempting to connect."""
        self.status = "connecting"
        self.save()

    def mark_stopped(self) -> None:
        """Mark connection as intentionally stopped."""
        self.status = "stopped"
        self.disconnected_at = timezone.now()
        self.save()

    def received_message(self) -> None:
        """Update timestamp when a message is received."""
        self.last_message_at = timezone.now()
        if self.status != "connected":
            self.mark_connected()
        else:
            self.save(update_fields=["last_message_at"])

    def should_reconnect(self) -> bool:
        """Check if we should attempt to reconnect."""
        return (
            self.status in ["disconnected", "error"]
            and self.reconnect_attempts < self.max_reconnect_attempts
        )

    def increment_reconnect_attempt(self) -> None:
        """Increment the reconnection attempt counter."""
        self.reconnect_attempts += 1
        self.save(update_fields=["reconnect_attempts"])

    @property
    def is_active(self) -> bool:
        """Check if the connection is currently active."""
        active: bool = self.status == "connected"
        return active

    @property
    def time_since_last_message(self) -> timedelta | None:
        """Get time since last message (or None if never received)."""
        if not self.last_message_at:
            return None
        duration: timedelta = timezone.now() - self.last_message_at
        return duration

    @property
    def connection_duration(self) -> timedelta | None:
        """Get how long the current connection has been active."""
        if not self.connected_at or self.status != "connected":
            return None
        duration: timedelta = timezone.now() - self.connected_at
        return duration
