"""Business logic service layer for django-micboard.

Decouples business logic from views, signals, and management commands.
Provides a unified interface for device management, polling, discovery,
location, and connection health monitoring.

Service Organization:
  - monitoring_access.py: User/group access control and location filtering
  - monitoring_service.py: Device health metrics, battery levels, signal strength
  - polling_api.py: Direct API server polling and device status updates
  - polling_service.py: High-level polling orchestration and broadcasting
  - manufacturer.py: Plugin-based device sync and deduplication
  - manufacturer_service.py: Abstract base for manufacturer service architecture
"""

from __future__ import annotations

# Implementation services
from .connection import ConnectionHealthService

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
from .hardware import HardwareService, NormalizedHardware
from .hardware_deduplication_service import (
    HardwareDeduplicationService,
    get_hardware_deduplication_service,
)
from .hardware_lifecycle import HardwareLifecycleManager, get_lifecycle_manager
from .hardware_sync_service import HardwareSyncService
from .location import LocationService
from .manufacturer import ManufacturerService
from .monitoring_access import MonitoringService as AccessControlService
from .monitoring_service import MonitoringService
from .performer import PerformerService
from .performer_assignment import PerformerAssignmentService
from .polling_api import PollingService as PollingAPIService
from .polling_service import PollingService, get_polling_service
from .utils import PaginatedResult, SyncResult, filter_by_search, paginate_queryset

__all__ = [
    # Core Services
    "AccessControlService",
    "ConnectionHealthService",
    "HardwareDeduplicationService",
    "HardwareService",
    "HardwareSyncService",
    "HardwareLifecycleManager",
    "ManufacturerService",
    "MonitoringService",
    "NormalizedHardware",
    "LocationService",
    "PerformerService",
    "PerformerAssignmentService",
    "PollingAPIService",
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
