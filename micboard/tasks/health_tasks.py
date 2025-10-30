"""
Health-related background tasks for the micboard app.
"""

# Health-related background tasks for the micboard app.
from __future__ import annotations

import logging
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import APIHealthLog, Manufacturer, RealTimeConnection
from micboard.signals.broadcast_signals import api_health_changed

logger = logging.getLogger(__name__)


def check_manufacturer_api_health(manufacturer_id: int):
    """
    Task to check a specific manufacturer's API health.
    """
    try:
        manufacturer = Manufacturer.objects.get(pk=manufacturer_id)
        plugin_class = get_manufacturer_plugin(manufacturer.code)
        plugin = plugin_class(manufacturer)
        health_status = plugin.get_client().check_health()

        # Log the health status
        APIHealthLog.objects.create(
            manufacturer=manufacturer,
            status=health_status.get("status", "unknown"),
            response_time=health_status.get("response_time"),
            error_message=health_status.get("error", ""),
            details=health_status,
        )

        # Optionally, store health status in cache or update a model field
        cache.set(f"api_health_{manufacturer.code}", health_status, timeout=60)
        logger.info("API health for %s: %s", manufacturer.code, health_status)

        # Emit api_health_changed signal
        api_health_changed.send(sender=None, manufacturer=manufacturer, health_data=health_status)

    except Manufacturer.DoesNotExist:
        logger.warning(
            "Manufacturer with ID %s not found for API health check task.", manufacturer_id
        )
    except Exception as e:
        logger.exception("Error checking API health for manufacturer ID %s: %s", manufacturer_id, e)


def check_realtime_connection_health():
    """
    Task to check health of real-time connections and clean up stale connections.
    """
    try:
        # Check for connections that haven't received messages recently
        stale_threshold = timezone.now() - timedelta(minutes=10)
        stale_connections = RealTimeConnection.objects.filter(
            status="connected", last_message_at__lt=stale_threshold
        )

        for connection in stale_connections:
            logger.warning(
                "Real-time connection for %s appears stale (last message: %s)",
                connection.receiver,
                connection.last_message_at,
            )
            connection.mark_disconnected("Connection appears stale - no messages received")

        # Check for connections that have been in error state too long
        error_threshold = timezone.now() - timedelta(hours=1)
        old_error_connections = RealTimeConnection.objects.filter(
            status="error", last_error_at__lt=error_threshold
        )

        for connection in old_error_connections:
            logger.info("Resetting old error state for connection: %s", connection.receiver)
            connection.status = "disconnected"
            connection.error_count = 0
            connection.error_message = ""
            connection.save()

        # Log summary
        active_connections = RealTimeConnection.objects.filter(status="connected").count()
        error_connections = RealTimeConnection.objects.filter(status="error").count()
        logger.info(
            "Real-time connection health check: %d active, %d errors, %d stale reset",
            active_connections,
            error_connections,
            stale_connections.count(),
        )

    except Exception as e:
        logger.exception("Error checking real-time connection health: %s", e)


def get_realtime_connection_status():
    """
    Get a summary of real-time connection statuses.

    Returns:
        dict: Summary of connection statuses
    """
    try:
        total = RealTimeConnection.objects.count()
        connected = RealTimeConnection.objects.filter(status="connected").count()
        connecting = RealTimeConnection.objects.filter(status="connecting").count()
        disconnected = RealTimeConnection.objects.filter(status="disconnected").count()
        error = RealTimeConnection.objects.filter(status="error").count()
        stopped = RealTimeConnection.objects.filter(status="stopped").count()

        return {
            "total": total,
            "connected": connected,
            "connecting": connecting,
            "disconnected": disconnected,
            "error": error,
            "stopped": stopped,
            "healthy_percentage": (connected / total * 100) if total > 0 else 0,
        }
    except Exception as e:
        logger.exception("Error getting real-time connection status: %s", e)
        return {"error": str(e)}
