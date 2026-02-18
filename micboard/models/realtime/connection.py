"""Models for tracking real-time connections and subscriptions."""

from __future__ import annotations

from typing import ClassVar

from django.db import models


class RealTimeConnection(models.Model):
    """Tracks real-time connections (SSE/WebSocket) for wireless chassis."""

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

    chassis = models.OneToOneField(
        "micboard.WirelessChassis",
        on_delete=models.CASCADE,
        related_name="realtime_connection",
        help_text="The wireless chassis this connection is for",
    )

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

    connected_at = models.DateTimeField(
        null=True, blank=True, help_text="When the connection was established"
    )
    last_message_at = models.DateTimeField(
        null=True, blank=True, help_text="When the last message was received"
    )
    disconnected_at = models.DateTimeField(
        null=True, blank=True, help_text="When the connection was lost"
    )

    error_message = models.TextField(
        blank=True, help_text="Last error message if connection failed"
    )
    error_count = models.PositiveIntegerField(
        default=0, help_text="Number of consecutive connection errors"
    )
    last_error_at = models.DateTimeField(
        null=True, blank=True, help_text="When the last error occurred"
    )

    reconnect_attempts = models.PositiveIntegerField(
        default=0, help_text="Number of reconnection attempts"
    )
    max_reconnect_attempts = models.PositiveIntegerField(
        default=5, help_text="Maximum number of reconnection attempts before giving up"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Real-Time Connection"
        verbose_name_plural = "Real-Time Connections"
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["status", "connection_type"]),
            models.Index(fields=["chassis", "status"]),
            models.Index(fields=["last_message_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.connection_type} - {self.chassis} ({self.status})"

    def mark_connected(self) -> None:
        """Mark connection as successfully established (delegates to service)."""
        from micboard.services.realtime.connection_service import mark_connected

        mark_connected(self)

    def mark_disconnected(self, error_message: str = "") -> None:
        """Mark connection as disconnected (delegates to service)."""
        from micboard.services.realtime.connection_service import mark_disconnected

        mark_disconnected(self, error_message)

    def mark_error(self, error_message: str) -> None:
        """Mark connection as having an error (delegates to service)."""
        from micboard.services.realtime.connection_service import mark_error

        mark_error(self, error_message)

    def mark_connecting(self) -> None:
        """Mark connection as attempting to connect (delegates to service)."""
        from micboard.services.realtime.connection_service import mark_connecting

        mark_connecting(self)

    def mark_stopped(self) -> None:
        """Mark connection as intentionally stopped (delegates to service)."""
        from micboard.services.realtime.connection_service import mark_stopped

        mark_stopped(self)

    def received_message(self) -> None:
        """Update timestamp when a message is received (delegates to service)."""
        from micboard.services.realtime.connection_service import received_message

        received_message(self)

    def should_reconnect(self) -> bool:
        """Check if we should attempt to reconnect (delegates to service)."""
        from micboard.services.realtime.connection_service import should_reconnect

        return should_reconnect(self)

    def increment_reconnect_attempt(self) -> None:
        """Increment the reconnection attempt counter (delegates to service)."""
        from micboard.services.realtime.connection_service import increment_reconnect_attempt

        increment_reconnect_attempt(self)

    @property
    def is_active(self) -> bool:
        """Check if the connection is currently active (delegates to service)."""
        from micboard.services.realtime.connection_service import is_active

        return is_active(self)

    @property
    def time_since_last_message(self):
        """Get time since last message (delegates to service)."""
        from micboard.services.realtime.connection_service import time_since_last_message

        return time_since_last_message(self)

    @property
    def connection_duration(self):
        """Get how long the current connection has been active (delegates to service)."""
        from micboard.services.realtime.connection_service import connection_duration

        return connection_duration(self)
