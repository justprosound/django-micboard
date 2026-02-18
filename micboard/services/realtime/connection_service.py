"""Service for RealTimeConnection business logic."""

from django.utils import timezone


def mark_connected(conn):
    conn.status = "connected"
    conn.connected_at = timezone.now()
    conn.last_message_at = timezone.now()
    conn.disconnected_at = None
    conn.error_count = 0
    conn.error_message = ""
    conn.reconnect_attempts = 0
    conn.save()


def mark_disconnected(conn, error_message: str = ""):
    conn.status = "disconnected"
    conn.disconnected_at = timezone.now()
    if error_message:
        conn.error_message = error_message
        conn.error_count += 1
        conn.last_error_at = timezone.now()
    conn.save()


def mark_error(conn, error_message: str):
    conn.status = "error"
    conn.error_message = error_message
    conn.error_count += 1
    conn.last_error_at = timezone.now()
    conn.save()


def mark_connecting(conn):
    conn.status = "connecting"
    conn.save()


def mark_stopped(conn):
    conn.status = "stopped"
    conn.disconnected_at = timezone.now()
    conn.save()


def received_message(conn):
    conn.last_message_at = timezone.now()
    if conn.status != "connected":
        mark_connected(conn)
    else:
        conn.save(update_fields=["last_message_at"])


def should_reconnect(conn):
    return (
        conn.status in ["disconnected", "error"]
        and conn.reconnect_attempts < conn.max_reconnect_attempts
    )


def increment_reconnect_attempt(conn):
    conn.reconnect_attempts += 1
    conn.save(update_fields=["reconnect_attempts"])


def is_active(conn):
    return conn.status == "connected"


def time_since_last_message(conn):
    if not conn.last_message_at:
        return None
    return timezone.now() - conn.last_message_at


def connection_duration(conn):
    if not conn.connected_at or conn.status != "connected":
        return None
    return timezone.now() - conn.connected_at
