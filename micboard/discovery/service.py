"""
Compatibility shim for micboard.discovery.service.

This module has been moved to micboard.services.discovery_service_new.
This file provides backwards compatibility for existing imports.
"""

from __future__ import annotations

import warnings

# Import from new location
from micboard.services.discovery_service_new import DiscoveryService  # noqa: F401

warnings.warn(
    "micboard.discovery.service is deprecated. "
    "Import from micboard.services.discovery_service_new instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["DiscoveryService"]
