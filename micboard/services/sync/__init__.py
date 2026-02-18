"""Synchronization and discovery services for django-micboard.

This package contains services for:
- Device discovery and orchestration
- Hardware synchronization with manufacturer APIs
- Device deduplication and conflict resolution
- Polling orchestration and coordination
- Network device probing and IP scanning
"""

from __future__ import annotations

from .base_polling_mixin import PollingMixin
from .device_probe_service import (
    DeviceAPIHealthChecker,
    DeviceProbeService,
    probe_device_ip,
)
from .discovery_orchestration_service import DiscoveryOrchestrationService
from .discovery_service import DiscoveryService
from .hardware_deduplication_service import (
    DeduplicationResult,
    HardwareDeduplicationService,
    get_hardware_deduplication_service,
)
from .hardware_sync_service import HardwareSyncService
from .polling_api import APIServerPollingService
from .polling_service import PollingService, get_polling_service

__all__ = [
    "APIServerPollingService",
    "DeduplicationResult",
    "DeviceAPIHealthChecker",
    "DeviceProbeService",
    "DiscoveryOrchestrationService",
    "DiscoveryService",
    "HardwareDeduplicationService",
    "HardwareSyncService",
    "PollingMixin",
    "PollingService",
    "get_hardware_deduplication_service",
    "get_polling_service",
    "probe_device_ip",
]
