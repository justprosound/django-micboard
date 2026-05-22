"""Device deduplication services for django-micboard.

Handles detection of duplicate devices, IP conflicts, and device movement
across the network. Provides authoritative device registry management.
"""

from __future__ import annotations

from .check import (
    check_api_id_conflicts,
    check_cross_vendor_api_id,
    check_device,
    find_duplicate,
)
from .queue import get_pending_approvals, queue_for_approval
from .result import DeduplicationResult
from .tracking import get_unacknowledged_movements, log_device_movement

__all__ = [
    "DeduplicationResult",
    "check_api_id_conflicts",
    "check_cross_vendor_api_id",
    "check_device",
    "find_duplicate",
    "get_pending_approvals",
    "get_unacknowledged_movements",
    "log_device_movement",
    "queue_for_approval",
]
