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
