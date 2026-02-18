"""Core domain services for django-micboard.

This package contains services for managing core domain entities:
- Hardware (chassis and wireless units)
- Locations and buildings
- Performers and assignments
- Device metadata and specifications
"""

from __future__ import annotations

from .charger_assignment import ChargerAssignmentService
from .device_metadata import DeviceMetadataAccessor, GenericMetadataAccessor, ShureMetadataAccessor
from .device_specs import DeviceSpec, DeviceSpecService
from .hardware import HardwareService, NormalizedHardware
from .location import LocationService
from .performer import PerformerService
from .performer_assignment import PerformerAssignmentService

__all__ = [
    "ChargerAssignmentService",
    "DeviceMetadataAccessor",
    "DeviceSpec",
    "DeviceSpecService",
    "GenericMetadataAccessor",
    "HardwareService",
    "LocationService",
    "NormalizedHardware",
    "PerformerAssignmentService",
    "PerformerService",
    "ShureMetadataAccessor",
]
