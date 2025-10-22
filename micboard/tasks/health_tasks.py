"""
Health-related background tasks for the micboard app.
"""

# Health-related background tasks for the micboard app.
from __future__ import annotations

import logging

from django.core.cache import cache

from micboard.manufacturers import get_manufacturer_plugin
from micboard.models import APIHealthLog, Manufacturer
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
