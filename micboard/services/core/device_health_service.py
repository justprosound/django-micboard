"""Device health monitoring service for lifecycle state management."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

from .hardware_lifecycle import HardwareLifecycleManager, HardwareStatus

if TYPE_CHECKING:
    from micboard.models import WirelessChassis, WirelessUnit

logger = logging.getLogger(__name__)


class DeviceHealthService:
    """Service for checking and maintaining device health.

    Monitors device responsiveness, auto-transitions between states
    (e.g., online ↔ offline), and provides bulk health assessment.
    Delegates state transitions to HardwareLifecycleManager.
    """

    def __init__(self, lifecycle_manager: HardwareLifecycleManager):
        """Initialize health service.

        Args:
            lifecycle_manager: HardwareLifecycleManager for state transitions
        """
        self._lifecycle_manager = lifecycle_manager

    def check_device_health(
        self,
        device: WirelessChassis | WirelessUnit,
        *,
        threshold_minutes: int = 5,
    ) -> str:
        """Check device health and auto-transition if needed.

        Args:
            device: Device to check
            threshold_minutes: Minutes without response before marking offline

        Returns:
            Current health status string
        """
        if device.status == HardwareStatus.MAINTENANCE.value:
            return "maintenance"

        if device.status == HardwareStatus.RETIRED.value:
            return "retired"

        if not device.last_seen:
            return "unknown"

        time_since = timezone.now() - device.last_seen
        threshold = timedelta(minutes=threshold_minutes)

        if time_since > threshold:
            if device.status != HardwareStatus.OFFLINE.value:
                self._lifecycle_manager.mark_offline(
                    device, reason=f"No response for {time_since.total_seconds():.0f}s"
                )
            return "offline"

        if device.status == HardwareStatus.OFFLINE.value:
            self._lifecycle_manager.mark_online(device)

        return device.status

    def bulk_health_check(
        self,
        devices: list[WirelessChassis | WirelessUnit],
        *,
        threshold_minutes: int = 5,
    ) -> dict[str, int]:
        """Check health of multiple devices efficiently.

        Args:
            devices: List of devices to check
            threshold_minutes: Offline threshold in minutes

        Returns:
            Dict with status counts (online, offline, degraded, maintenance, other)
        """
        results: dict[str, int] = {
            "online": 0,
            "offline": 0,
            "degraded": 0,
            "maintenance": 0,
            "other": 0,
        }

        for device in devices:
            status = self.check_device_health(device, threshold_minutes=threshold_minutes)
            if status in results:
                results[status] += 1
            else:
                results["other"] += 1

        logger.info(
            f"Bulk health check: {len(devices)} devices",
            extra={"device_count": len(devices), "results": results},
        )

        return results
