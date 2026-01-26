# file: micboard/models/monitoring/__init__.py
"""Monitoring, assignments, and alert models."""

from .alert import Alert, UserAlertPreference
from .assignment import DeviceAssignment
from .group import Group, MonitoringGroup

# Backwards-compatible alias expected by higher-level imports
Assignment = DeviceAssignment

__all__ = [
    "Alert",
    "Assignment",
    "DeviceAssignment",
    "UserAlertPreference",
    "Group",
    "MonitoringGroup",
]
