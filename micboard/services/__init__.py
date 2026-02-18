"""Business logic service layer for django-micboard.

Decouples business logic from views, signals, and management commands.
Provides a unified interface for device management, polling, discovery,
location, and connection health monitoring.

Service Organization (Functional Subfolders):
  - core/: Hardware, Location, Performer, Device specs
  - sync/: Discovery, Polling, Deduplication
  - monitoring/: Connection health, Alerts, Uptime
  - maintenance/: Audit, Logging, EFIS import
  - manufacturer/: Plugin registry, Manufacturer config
  - notification/: Broadcasting, Email, Signal emitter
  - shared/: Utilities, Exceptions, Tenant filters
"""

from __future__ import annotations

# Core services
from .core.hardware import HardwareService, NormalizedHardware
from .core.hardware_lifecycle import HardwareLifecycleManager, get_lifecycle_manager
from .core.location import LocationService
from .core.performer import PerformerService
from .core.performer_assignment import PerformerAssignmentService

# Manufacturer services
from .manufacturer.manufacturer import ManufacturerService

# Monitoring services
from .monitoring.connection import ConnectionHealthService
from .monitoring.monitoring_access import MonitoringService as AccessControlService
from .monitoring.monitoring_service import MonitoringService

# Shared utilities and exceptions
from .shared.exceptions import (
    ConnectionError,
    DiscoveryError,
    HardwareNotFoundError,
    LocationAlreadyExistsError,
    LocationNotFoundError,
    ManufacturerPluginError,
    MicboardServiceError,
)
from .shared.pagination import PaginatedResult, filter_by_search, paginate_queryset
from .shared.sync_utils import SyncResult

# Sync services
from .sync.device_probe_service import (
    DeviceAPIHealthChecker,
    DeviceProbeService,
    probe_device_ip,
)
from .sync.hardware_deduplication_service import (
    HardwareDeduplicationService,
    get_hardware_deduplication_service,
)
from .sync.hardware_sync_service import HardwareSyncService
from .sync.polling_api import APIServerPollingService
from .sync.polling_service import PollingService, get_polling_service

__all__ = [
    # Core Services
    "AccessControlService",
    "APIServerPollingService",
    "ConnectionHealthService",
    "DeviceAPIHealthChecker",
    "DeviceProbeService",
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
    "PollingService",
    # Service Accessors
    "get_polling_service",
    "get_lifecycle_manager",
    "get_hardware_deduplication_service",
    "probe_device_ip",
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
