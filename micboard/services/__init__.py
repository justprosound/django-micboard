"""Business logic service layer for django-micboard.

Decouples business logic from views, signals, and management commands.
Provides a unified interface for device management, polling, discovery,
location, and connection health monitoring.
"""

from __future__ import annotations

# Implementation services
from .assignment import AssignmentService
from .connection import ConnectionHealthService
from .device_service import DeviceService
from .discovery import DiscoveryService

# Core exceptions
from .exceptions import (
    AssignmentAlreadyExistsError,
    AssignmentNotFoundError,
    ConnectionError,
    DeviceNotFoundError,
    DiscoveryError,
    LocationAlreadyExistsError,
    LocationNotFoundError,
    ManufacturerPluginError,
    MicboardServiceError,
)
from .location import LocationService
from .manufacturer import ManufacturerService
from .monitoring_service import MonitoringService
from .polling_service import PollingService, get_polling_service
from .synchronization_service import SynchronizationService
from .utils import PaginatedResult, SyncResult, filter_by_search, paginate_queryset

__all__ = [
    # Core Services
    "AssignmentService",
    "ConnectionHealthService",
    "DeviceService",
    "DiscoveryService",
    "LocationService",
    "ManufacturerService",
    "MonitoringService",
    "PollingService",
    "SynchronizationService",
    # Service Accessors
    "get_polling_service",
    # Utilities
    "SyncResult",
    "PaginatedResult",
    "paginate_queryset",
    "filter_by_search",
    # Exceptions
    "MicboardServiceError",
    "AssignmentAlreadyExistsError",
    "AssignmentNotFoundError",
    "ConnectionError",
    "DeviceNotFoundError",
    "DiscoveryError",
    "LocationAlreadyExistsError",
    "LocationNotFoundError",
    "ManufacturerPluginError",
]
