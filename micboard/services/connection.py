"""Connection health service for real-time connection monitoring.

Manages real-time connection lifecycle, health checks, and status tracking.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import QuerySet
from django.utils.timezone import now

from micboard.models import RealTimeConnection


class ConnectionHealthService:
    """Business logic for connection health monitoring and status management."""

    @staticmethod
    def create_connection(
        *, chassis: WirelessChassis, connection_type: str, status: str = "connecting"
    ) -> RealTimeConnection:
        """Create a new real-time connection.

        Args:
            chassis: WirelessChassis instance.
            connection_type: Type of connection ('sse', 'websocket', etc.).
            status: Initial connection status.

        Returns:
            Created RealTimeConnection object.
        """
        return RealTimeConnection.objects.create(
            chassis=chassis,
            connection_type=connection_type,
            status=status,
            connected_at=now() if status == "connected" else None,
        )

    @staticmethod
    def update_connection_status(
        *, connection: RealTimeConnection, status: str
    ) -> RealTimeConnection:
        """Update connection status.

        Args:
            connection: RealTimeConnection instance.
            status: New status ('connecting', 'connected', 'disconnected', 'error').

        Returns:
            Updated RealTimeConnection object.
        """
        connection.status = status

        if status == "connected":
            connection.connected_at = now()
            connection.last_message_at = now()
            connection.error_count = 0
        elif status in ("disconnected", "error"):
            connection.disconnected_at = now()
            if status == "error":
                connection.error_count = (connection.error_count or 0) + 1

        connection.save()
        return connection

    @staticmethod
    def record_heartbeat(*, connection: RealTimeConnection) -> None:
        """Record a successful heartbeat for a connection.

        Args:
            connection: RealTimeConnection instance.
        """
        connection.last_message_at = now()
        connection.save(update_fields=["last_message_at", "updated_at"])

    @staticmethod
    def record_error(*, connection: RealTimeConnection, error_message: str) -> None:
        """Record an error for a connection.

        Args:
            connection: RealTimeConnection instance.
            error_message: Error description.
        """
        connection.error_message = error_message
        connection.error_count = (connection.error_count or 0) + 1
        connection.save(update_fields=["error_message", "error_count", "updated_at"])

    @staticmethod
    def is_healthy(*, connection: RealTimeConnection, heartbeat_timeout_seconds: int = 60) -> bool:
        """Check if connection is healthy.

        A connection is healthy if:
        - Status is 'connected'
        - Last message is recent (within timeout window)

        Args:
            connection: RealTimeConnection instance.
            heartbeat_timeout_seconds: Timeout window for heartbeat.

        Returns:
            True if connection is healthy, False otherwise.
        """
        if connection.status != "connected":
            return False

        if not connection.last_message_at:
            return False

        timeout = now() - timedelta(seconds=heartbeat_timeout_seconds)
        return connection.last_message_at > timeout

    @staticmethod
    def get_active_connections() -> QuerySet:
        """Get all active (connected) connections.

        Returns:
            QuerySet of connected RealTimeConnection objects.
        """
        return RealTimeConnection.objects.filter(status="connected")

    @staticmethod
    def get_unhealthy_connections(*, heartbeat_timeout_seconds: int = 60) -> QuerySet:
        """Get all unhealthy connections.

        Args:
            heartbeat_timeout_seconds: Heartbeat timeout threshold.

        Returns:
            QuerySet of unhealthy RealTimeConnection objects.
        """
        timeout = now() - timedelta(seconds=heartbeat_timeout_seconds)
        return RealTimeConnection.objects.filter(status="connected", last_message_at__lt=timeout)

    @staticmethod
    def get_connections_by_manufacturer(*, manufacturer_code: str) -> QuerySet:
        """Get connections for a specific manufacturer.

        Args:
            manufacturer_code: Manufacturer code.

        Returns:
            QuerySet of RealTimeConnection objects.
        """
        return RealTimeConnection.objects.filter(chassis__manufacturer__code=manufacturer_code).order_by(
            "-created_at"
        )

    @staticmethod
    def cleanup_stale_connections(*, max_age_hours: int = 24) -> int:
        """Clean up old disconnected connections.

        Args:
            max_age_hours: Delete connections older than this (in hours).

        Returns:
            Number of deleted connections.
        """
        cutoff_time = now() - timedelta(hours=max_age_hours)
        deleted_count, _ = RealTimeConnection.objects.filter(
            status="disconnected", disconnected_at__lt=cutoff_time
        ).delete()
        return deleted_count

    @staticmethod
    def get_connection_uptime(*, connection: RealTimeConnection) -> timedelta | None:
        """Calculate connection uptime duration.

        Args:
            connection: RealTimeConnection instance.

        Returns:
            timedelta of uptime, or None if not connected or no connection time recorded.
        """
        if not connection.connected_at:
            return None

        if connection.status == "connected":
            return now() - connection.connected_at

        if connection.disconnected_at:
            return connection.disconnected_at - connection.connected_at

        return None

    @staticmethod
    def get_connection_stats() -> dict[str, Any]:
        """Get overall connection statistics.

        Returns:
            Dictionary with connection stats:
            {
                'total_connections': int,
                'active_connections': int,
                'error_connections': int,
                'avg_error_count': float | None,
                'by_manufacturer': dict[str, int]
            }
        """
        total = RealTimeConnection.objects.count()
        active = RealTimeConnection.objects.filter(status="connected").count()
        errors = RealTimeConnection.objects.filter(status="error").count()

        connections = RealTimeConnection.objects.all()
        avg_errors = None
        if connections.exists():
            total_errors = sum(c.error_count or 0 for c in connections)
            avg_errors = total_errors / total if total > 0 else 0

        by_manufacturer = {}
        for mfg in RealTimeConnection.objects.values_list(
            "chassis__manufacturer__code", flat=True
        ).distinct():
            if mfg:
                by_manufacturer[mfg] = RealTimeConnection.objects.filter(chassis__manufacturer__code=mfg).count()

        return {
            "total_connections": total,
            "active_connections": active,
            "error_connections": errors,
            "avg_error_count": avg_errors,
            "by_manufacturer": by_manufacturer,
        }

    @staticmethod
    def get_connections_for_manufacturer(*, manufacturer_code: str) -> QuerySet[RealTimeConnection]:
        """Get all connections for a manufacturer (alias for get_connections_by_manufacturer)."""
        return ConnectionHealthService.get_connections_by_manufacturer(
            manufacturer_code=manufacturer_code
        )

    @staticmethod
    def update_heartbeat(*, connection: RealTimeConnection) -> None:
        """Update the heartbeat for a connection (alias for record_heartbeat)."""
        ConnectionHealthService.record_heartbeat(connection=connection)

    @staticmethod
    def is_connection_healthy(
        *, connection: RealTimeConnection, heartbeat_timeout_seconds: int = 60
    ) -> bool:
        """Check if a connection is healthy (alias for is_healthy)."""
        return ConnectionHealthService.is_healthy(
            connection=connection, heartbeat_timeout_seconds=heartbeat_timeout_seconds
        )

    @staticmethod
    def reset_connection_errors(*, connection: RealTimeConnection) -> RealTimeConnection:
        """Reset error count for a connection."""
        connection.error_count = 0
        connection.last_error = None
        connection.save(update_fields=["error_count", "last_error"])
        return connection
