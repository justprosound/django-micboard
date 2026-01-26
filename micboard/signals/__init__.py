"""Signal handlers and exports for the micboard app.

This module imports the individual signal handler modules to register handlers
and exposes commonly-used signal names for external code and tests. Tests
patch `micboard.signals.logger`, so a package-level `logger` is provided.
"""

import logging

from asgiref.sync import async_to_sync
from django.core.cache import cache

try:
    from channels.layers import get_channel_layer
except ImportError:
    # Channels not installed, provide a no-op function
    def get_channel_layer():
        return None


# Import signal modules to register handlers
# Import new device lifecycle handlers (Phase 4)
from . import (
    broadcast_signals,
    device_signals,
    discovery_signals,
    handlers,
    user_signals,
)

# Import signals for external use
from .broadcast_signals import api_health_changed, devices_polled
from .device_signals import (
    assignment_saved,
    rf_channel_saved,
    wireless_chassis_deleted,
    wireless_chassis_pre_delete,
    wireless_chassis_saved,
)

# Package-level logger (tests may patch this). Define before importing submodules
# to avoid circular imports where submodules import `from . import logger`.
logger = logging.getLogger(__name__)


__all__ = [
    "api_health_changed",
    "assignment_saved",
    "async_to_sync",
    "broadcast_signals",
    "cache",
    "device_signals",
    "discovery_signals",
    "rf_channel_saved",
    "devices_polled",
    "get_channel_layer",
    "handlers",
    "logger",
    "user_signals",
    "wireless_chassis_deleted",
    "wireless_chassis_pre_delete",
    "wireless_chassis_saved",
]
