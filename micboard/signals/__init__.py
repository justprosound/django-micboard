"""
Signal handlers and exports for the micboard app.

This module imports the individual signal handler modules to register handlers
and exposes commonly-used signal names for external code and tests. Tests
patch `micboard.signals.logger`, so a package-level `logger` is provided.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache

# Import signal modules to register handlers
from . import broadcast_signals, device_signals, discovery_signals, request_signals, user_signals
# Import new device lifecycle handlers (Phase 4)
from . import handlers  # noqa: F401

# Import signals for external use
from .broadcast_signals import api_health_changed, devices_polled
from .device_signals import (
    assignment_saved,
    channel_saved,
    receiver_deleted,
    receiver_pre_delete,
    receiver_saved,
)
from .request_signals import (
    add_discovery_ips_requested,
    device_detail_requested,
    discover_requested,
    discovery_candidates_requested,
    refresh_requested,
)

# Package-level logger (tests may patch this). Define before importing submodules
# to avoid circular imports where submodules import `from . import logger`.
logger = logging.getLogger(__name__)


__all__ = [
    "add_discovery_ips_requested",
    "api_health_changed",
    "assignment_saved",
    "async_to_sync",
    "cache",
    "channel_saved",
    "device_detail_requested",
    "devices_polled",
    "discover_requested",
    "discovery_candidates_requested",
    "get_channel_layer",
    "logger",
    "receiver_deleted",
    "receiver_pre_delete",
    "receiver_saved",
    "refresh_requested",
]
