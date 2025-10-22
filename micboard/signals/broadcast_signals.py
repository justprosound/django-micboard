"""
Broadcast-related signal handlers for the micboard app.
"""

# Broadcast-related signal handlers for the micboard app.
from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.dispatch import Signal, receiver

logger = logging.getLogger(__name__)

# Signal emitted when devices are polled/updated from a manufacturer API.
# Payload should include 'manufacturer' (Manufacturer instance or code)
# and 'data' (serialized structure for broadcasting).
devices_polled = Signal()

# Signal emitted when a Manufacturer's API health status changes.
# Payload should include 'manufacturer' (Manufacturer instance) and 'health_data' (dict).
api_health_changed = Signal()


@receiver(devices_polled)
def handle_devices_polled(sender, *, manufacturer=None, data=None, **kwargs):
    """Broadcast polled device data to WebSocket clients.

    The signal centralizes broadcasting logic so callers (management commands,
    discovery sync) don't need to interact with Channels directly.
    """
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.debug("No channel layer configured; skipping broadcast")
            return

        async_to_sync(channel_layer.group_send)(
            "micboard_updates", {"type": "device_update", "data": data}
        )
        logger.debug(
            "Broadcasted device update for manufacturer %s",
            getattr(manufacturer, "code", str(manufacturer)),
        )
    except Exception:
        logger.exception("Failed to broadcast devices_polled signal payload")


@receiver(api_health_changed)
def handle_api_health_changed(sender, *, manufacturer=None, health_data=None, **kwargs):
    """Broadcast API health status to WebSocket clients."""
    try:
        channel_layer = get_channel_layer()
        if not channel_layer:
            logger.debug("No channel layer configured; skipping API health broadcast")
            return

        async_to_sync(channel_layer.group_send)(
            "micboard_updates",
            {
                "type": "api_health_update",
                "manufacturer_code": getattr(manufacturer, "code", None),
                "health_data": health_data,
            },
        )
        logger.debug(
            "Broadcasted API health update for manufacturer %s: %s",
            getattr(manufacturer, "code", str(manufacturer)),
            health_data,
        )
    except Exception:
        logger.exception("Failed to broadcast api_health_changed signal payload")
