"""Business logic service layer for django-micboard.

Decouples business logic from views, signals, and management commands.
Provides a unified interface for device management, polling, discovery,
location, and connection health monitoring.
"""

from __future__ import annotations

# Implementation services
from .connection import ConnectionHealthService
from .hardware_deduplication_service import HardwareDeduplicationService, get_hardware_deduplication_service
from .hardware import HardwareService, NormalizedHardware
from .hardware_lifecycle import HardwareLifecycleManager, get_lifecycle_manager
from .hardware_sync_service import HardwareSyncService

# Core exceptions
from .exceptions import (
    ConnectionError,
    DiscoveryError,
    HardwareNotFoundError,
    LocationAlreadyExistsError,
    LocationNotFoundError,
    ManufacturerPluginError,
    MicboardServiceError,
)
from .location import LocationService
from .manufacturer import ManufacturerService
from .monitoring_service import MonitoringService
from .performer import PerformerService
from .performer_assignment import PerformerAssignmentService
from .polling_service import PollingService, get_polling_service
from .hardware_sync_service import HardwareSyncService
from .utils import PaginatedResult, SyncResult, filter_by_search, paginate_queryset

__all__ = [
    # Core Services
    "ConnectionHealthService",
    "HardwareDeduplicationService",
    "HardwareService",
    "HardwareSyncService",
    "HardwareLifecycleManager",
    "NormalizedHardware",
    "LocationService",
    "ManufacturerService",
    "MonitoringService",
    "PerformerService",
    "PerformerAssignmentService",
    "PollingService",
    # Service Accessors
    "get_polling_service",
    "get_lifecycle_manager",
    "get_hardware_deduplication_service",
    # Utilities
    "SyncResult",
    "PaginatedResult",
    "paginate_queryset",
    "filter_by_search",
    # Exceptions
    "MicboardServiceError",
    "ConnectionError",
    "HardwareNotFoundError",
    "DiscoveryError",
    "LocationAlreadyExistsError",
    "LocationNotFoundError",
    "ManufacturerPluginError",
]
