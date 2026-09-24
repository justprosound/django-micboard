"""Models for tracking real-time connections and subscriptions."""

from __future__ import annotations

from datetime import timedelta
from typing import ClassVar

from django.db import models
from django.db.models import F
from django.utils import timezone


class RealTimeConnectionQuerySet(models.QuerySet["RealTimeConnection"]):
    """Every state a realtime connection can be moved into, defined once.

    Each transition is a bulk update, so a single row held by the subscription runner and a
    changelist selection made in the admin go through the same definition and cannot drift
    into different spellings of the same state.
    """

    def mark_connecting(self) -> int:
        """Record that a connection attempt is in progress.

        The error history is deliberately preserved: a reconnect is not yet a success.
        """
        return self.update(status="connecting", updated_at=timezone.now())

    def mark_connected(self) -> int:
        """Record an established connection and clear every trace of the last failure."""
        now = timezone.now()
        return self.update(
            status="connected",
            connected_at=now,
            last_message_at=now,
            disconnected_at=None,
            error_count=0,
            error_message="",
            reconnect_attempts=0,
            updated_at=now,
        )

    def record_message(self) -> int:
        """Record message activity, establishing a connection that was still pending.

        Live rows are moved first. Establishing pending rows first would leave them matching
        the `status="connected"` filter as well, counting one row twice.
        """
        now = timezone.now()
        moved = self.filter(status="connected").update(last_message_at=now, updated_at=now)
        # A stopped row is a decision an operator made, and stopping does not tear down a
        # live subscription, so a late callback must not put it back. Error and disconnected
        # rows are recovered, which is what the per-row helper this replaced did.
        established = self.exclude(status__in=("connected", "stopped")).mark_connected()
        return moved + established

    def mark_error(self, error_message: str) -> int:
        """Record one redacted transport error, counting consecutive failures."""
        now = timezone.now()
        return self.update(
            status="error",
            error_message=error_message,
            error_count=F("error_count") + 1,
            last_error_at=now,
            updated_at=now,
        )

    def mark_disconnected(self) -> int:
        """Record an unintentional loss of the connection."""
        now = timezone.now()
        return self.update(status="disconnected", disconnected_at=now, updated_at=now)

    def mark_stopped(self) -> int:
        """Record an intentional connection stop."""
        now = timezone.now()
        return self.update(status="stopped", disconnected_at=now, updated_at=now)

    def reset_errors(self) -> int:
        """Clear a stale error count without claiming the connection is back."""
        return self.update(error_count=0, error_message="", updated_at=timezone.now())


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

    objects = RealTimeConnectionQuerySet.as_manager()

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

    @property
    def connected_duration(self) -> timedelta | None:
        """Return how long this connection has been up, or none outside a live session."""
        if not self.connected_at or self.status != "connected":
            return None
        return timezone.now() - self.connected_at

    @property
    def time_since_last_message(self) -> timedelta | None:
        """Return elapsed time since the latest message, when one exists."""
        if not self.last_message_at:
            return None
        return timezone.now() - self.last_message_at
