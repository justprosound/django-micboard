"""Service for RealTimeConnection business logic."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from micboard.models.realtime.connection import RealTimeConnection


def mark_connected(conn: RealTimeConnection) -> None:
    """Record a successful connection and reset its consecutive error state."""
    now = timezone.now()
    conn.status = "connected"
    conn.connected_at = now
    conn.last_message_at = now
    conn.disconnected_at = None
    conn.error_count = 0
    conn.error_message = ""
    conn.reconnect_attempts = 0
    conn.save()


def mark_error(conn: RealTimeConnection, error_message: str) -> None:
    """Record one redacted transport error for an active connection row."""
    conn.status = "error"
    conn.error_message = error_message
    conn.error_count += 1
    conn.last_error_at = timezone.now()
    conn.save()


def mark_connecting(conn: RealTimeConnection) -> None:
    """Mark a connection attempt as in progress."""
    conn.status = "connecting"
    conn.save()


def mark_stopped(conn: RealTimeConnection) -> None:
    """Record an intentional connection stop."""
    conn.status = "stopped"
    conn.disconnected_at = timezone.now()
    conn.save()


def received_message(conn: RealTimeConnection) -> None:
    """Record message activity and establish a previously pending connection."""
    if conn.status != "connected":
        mark_connected(conn)
    else:
        conn.last_message_at = timezone.now()
        conn.save(update_fields=["last_message_at"])


def time_since_last_message(conn: RealTimeConnection) -> timedelta | None:
    """Return elapsed time since the latest message, when one exists."""
    if not conn.last_message_at:
        return None
    return timezone.now() - conn.last_message_at


def connection_duration(conn: RealTimeConnection) -> timedelta | None:
    """Return the current connected duration, or none outside an active session."""
    if not conn.connected_at or conn.status != "connected":
        return None
    return timezone.now() - conn.connected_at
