"""Uptime tracking service for device availability monitoring.

Provides lightweight uptime calculation without database bloat.
Uses status changes (not every poll) to minimize writes.

Key insight: Only write to DB when status CHANGES, not on every poll.
Calculates: ~29 writes/day instead of 2880 writes/day per device.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, List

from django.utils import timezone

from micboard.models import WirelessChassis

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class UptimeService:
    """Calculate chassis uptime without excessive database writes.

    Traditional approach: Write on every poll (2880/day per device)
    This approach: Write only on status changes (~29/day per device)
    Storage: 99% reduction vs django-simple-history audit trail
    """

    @staticmethod
    def record_status_change(device: WirelessChassis, online: bool) -> bool:
        """Record status change and update uptime metrics.

        Only writes to DB when status CHANGES (not on every poll).

        Args:
            device: WirelessChassis instance
            online: Current online status from API

        Returns:
            True if status changed and written to DB, False if no change
        """
        previous_status = device.is_online

        # No change = no write
        if previous_status == online:
            return False

        device.is_online = online
        now = timezone.now()

        if online:
            # Transitioned: offline → online
            device.last_online_at = now
            device.last_offline_at = None
            logger.info(
                "Device %s (%s) came ONLINE",
                device.name,
                device.ip,
            )
        else:
            # Transitioned: online → offline
            device.last_offline_at = now

            # Calculate uptime for this session
            if device.last_online_at:
                uptime_delta = now - device.last_online_at
                uptime_minutes = int(uptime_delta.total_seconds() / 60)
                device.total_uptime_minutes += uptime_minutes

                logger.info(
                    "Device %s (%s) went OFFLINE after %d minutes online",
                    device.name,
                    device.ip,
                    uptime_minutes,
                )

        # Single write per status change (vs 1 write per poll)
        device.save(
            update_fields=[
                "is_online",
                "last_online_at",
                "last_offline_at",
                "total_uptime_minutes",
            ]
        )
        return True

    @staticmethod
    def get_uptime_percentage(device: WirelessChassis, *, days: int = 7) -> float:
        """Calculate uptime percentage over specified days using movements.

        This leverages the existing DeviceMovementLog to detect downtime
        without requiring additional database writes.

        Args:
            device: WirelessChassis instance
            days: Number of days to analyze (default: 7)

        Returns:
            Uptime percentage (0-100)
        """
        from micboard.models import DeviceMovementLog

        cutoff = timezone.now() - timedelta(days=days)
        total_time = timezone.now() - cutoff

        # Get movements in period
        movements = DeviceMovementLog.objects.filter(
            device=device,
            detected_at__gte=cutoff,
        ).select_related("device")

        # Calculate offline duration from movements
        offline_time = timedelta()

        for movement in movements:
            if movement.old_ip and movement.new_ip:
                # IP movement = downtime until acknowledged or next detection
                detection_time = timezone.now() - movement.detected_at
                # Conservative estimate: time until acknowledged or 1 hour
                offline_duration = (
                    movement.acknowledged_at - movement.detected_at
                    if movement.acknowledged_at
                    else min(detection_time, timedelta(hours=1))
                )
                offline_time += offline_duration

        if total_time.total_seconds() == 0:
            return 100.0

        uptime_pct = ((total_time - offline_time) / total_time) * 100
        return max(0.0, min(100.0, uptime_pct))

    @staticmethod
    def get_uptime_percentage_7d(device: WirelessChassis) -> float:
        """Get 7-day uptime percentage."""
        return UptimeService.get_uptime_percentage(device, days=7)

    @staticmethod
    def get_uptime_percentage_30d(device: WirelessChassis) -> float:
        """Get 30-day uptime percentage."""
        return UptimeService.get_uptime_percentage(device, days=30)

    @staticmethod
    def get_session_uptime(device: WirelessChassis) -> dict:
        """Get current session uptime (time online since last boot/discovery).

        Args:
            device: WirelessChassis instance

        Returns:
            Dict with:
            - is_online: Current status
            - uptime_minutes: Minutes in current session
            - uptime_hours: Hours in current session
            - uptime_formatted: Human-readable format
            - started_at: When current session started
        """
        if not device.is_online or not device.last_online_at:
            return {
                "is_online": False,
                "uptime_minutes": 0,
                "uptime_hours": 0,
                "uptime_formatted": "Offline",
                "started_at": None,
            }

        now = timezone.now()
        uptime_delta = now - device.last_online_at
        total_minutes = int(uptime_delta.total_seconds() / 60)
        total_hours = total_minutes / 60

        # Format human-readable
        days = total_minutes // (24 * 60)
        hours = (total_minutes % (24 * 60)) // 60
        minutes = total_minutes % 60

        if days > 0:
            formatted = f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            formatted = f"{hours}h {minutes}m"
        else:
            formatted = f"{minutes}m"

        return {
            "is_online": True,
            "uptime_minutes": total_minutes,
            "uptime_hours": total_hours,
            "uptime_formatted": formatted,
            "started_at": device.last_online_at,
        }

    @staticmethod
    def get_uptime_summary(device: WirelessChassis) -> dict:
        """Get comprehensive uptime summary.

        Returns:
            Dict with current session, 7-day, 30-day uptime metrics
        """
        return {
            "session": UptimeService.get_session_uptime(device),
            "total_minutes_tracked": device.total_uptime_minutes,
            "uptime_7d_percent": UptimeService.get_uptime_percentage_7d(device),
            "uptime_30d_percent": UptimeService.get_uptime_percentage_30d(device),
            "last_online_at": device.last_online_at,
            "last_offline_at": device.last_offline_at,
        }


class BulkUptimeCalculator:
    """Efficiently calculate uptime for multiple devices.

    Useful for dashboards and bulk reporting.
    """

    @staticmethod
    def get_uptime_summary_batch(devices: List[WirelessChassis], *, days: int = 7) -> dict:
        """Calculate uptime for batch of devices efficiently.

        Args:
            devices: List of WirelessChassis objects
            days: Number of days to analyze

        Returns:
            Dict mapping device_id -> uptime_percentage
        """
        from micboard.models import DeviceMovementLog

        cutoff = timezone.now() - timedelta(days=days)
        total_time = timezone.now() - cutoff

        # Batch query movements
        device_ids = [d.id for d in devices]
        movements = DeviceMovementLog.objects.filter(
            device_id__in=device_ids,
            detected_at__gte=cutoff,
        ).values("device_id", "old_ip", "new_ip", "detected_at", "acknowledged_at")

        # Build movement lookup
        offline_by_device = {}
        for movement in movements:
            device_id = movement["device_id"]
            if device_id not in offline_by_device:
                offline_by_device[device_id] = timedelta()

            if movement["old_ip"] and movement["new_ip"]:
                offline_duration = (
                    movement["acknowledged_at"] - movement["detected_at"]
                    if movement["acknowledged_at"]
                    else timedelta(hours=1)
                )
                offline_by_device[device_id] += offline_duration

        # Calculate percentages
        results = {}
        for device in devices:
            offline_time = offline_by_device.get(device.id, timedelta())
            uptime_pct = ((total_time - offline_time) / total_time) * 100
            results[device.id] = max(0.0, min(100.0, uptime_pct))

        return results

    @staticmethod
    def get_manufacturer_uptime_stats(manufacturer, *, days: int = 7) -> dict:
        """Get uptime statistics for all devices from a manufacturer.

        Args:
            manufacturer: Manufacturer instance
            days: Number of days to analyze

        Returns:
            Dict with aggregate stats and per-device breakdown
        """
        receivers = WirelessChassis.objects.filter(manufacturer=manufacturer)
        uptime_dict = BulkUptimeCalculator.get_uptime_summary_batch(list(receivers), days=days)

        if not uptime_dict:
            return {
                "total_devices": 0,
                "online_devices": 0,
                "offline_devices": 0,
                "average_uptime_percent": 0,
                "devices": {},
            }

        uptimes = list(uptime_dict.values())
        return {
            "total_devices": len(receivers),
            "online_devices": receivers.filter(is_online=True).count(),
            "offline_devices": receivers.filter(is_online=False).count(),
            "average_uptime_percent": sum(uptimes) / len(uptimes),
            "min_uptime_percent": min(uptimes),
            "max_uptime_percent": max(uptimes),
            "devices": uptime_dict,
        }
