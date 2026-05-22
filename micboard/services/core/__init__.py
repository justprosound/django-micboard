"""Core domain services for django-micboard.

This package contains services for managing core domain entities:
- Hardware (chassis and wireless units)
- Locations and buildings
- Performers and assignments
- Device metadata and specifications
"""

from __future__ import annotations

from .charger_assignment import ChargerAssignmentService
from .device_api_sync_service import DeviceAPISyncService
from .device_health_service import DeviceHealthService
from .device_metadata import DeviceMetadataAccessor, GenericMetadataAccessor, ShureMetadataAccessor
from .device_specs import DeviceSpec, DeviceSpecService
from .hardware import HardwareService, NormalizedHardware
from .hardware_lifecycle import HardwareLifecycleManager, get_lifecycle_manager
from .hardware_post_save_hooks import HardwarePostSaveHooks
from .hardware_query import HardwareQueryService
from .hardware_sync import HardwareSyncService
from .location import LocationService
from .performer import PerformerService
from .performer_assignment import PerformerAssignmentService

__all__ = [
    "ChargerAssignmentService",
    "DeviceAPISyncService",
    "DeviceHealthService",
    "DeviceMetadataAccessor",
    "DeviceSpec",
    "DeviceSpecService",
    "GenericMetadataAccessor",
    "HardwareLifecycleManager",
    "HardwarePostSaveHooks",
    "HardwareQueryService",
    "HardwareService",
    "HardwareSyncService",
    "LocationService",
    "NormalizedHardware",
    "PerformerAssignmentService",
    "PerformerService",
    "ShureMetadataAccessor",
    "get_lifecycle_manager",
]
