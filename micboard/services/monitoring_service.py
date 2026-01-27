"""Monitoring service for device health and alerts.

Provides methods for monitoring device status, battery levels, signal quality,
and generating health reports. Used by dashboards and alerting systems.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q

from micboard.models import RFChannel, WirelessChassis, WirelessUnit


class MonitoringService:
    """Service for monitoring device health and generating alerts."""

    @staticmethod
    def get_devices_with_low_battery(*, threshold: int = 25) -> list[WirelessUnit]:
        """Get wireless units with battery levels below threshold.

        Args:
            threshold: Battery percentage threshold (0-100)

        Returns:
            List of wireless units with low battery
        """
        # Get wireless units with low battery by checking battery field
        # Battery field is 0-255, convert threshold to same scale
        battery_threshold = int(threshold * 255 / 100)
        return list(
            WirelessUnit.objects.filter(
                Q(battery__lt=battery_threshold) & ~Q(battery__isnull=True)
            ).select_related(
                "assigned_resource__chassis__manufacturer", "assigned_resource__chassis__location"
            )
        )

    @staticmethod
    def get_devices_with_weak_signal(*, threshold: int = -80) -> list[RFChannel]:
        """Get channels with RF signal strength below threshold.

        Args:
            threshold: Signal strength threshold in dB

        Returns:
            List of channels with weak signal
        """
        return list(
            RFChannel.objects.filter(
                Q(rf_signal_strength__lt=threshold) & ~Q(rf_signal_strength__isnull=True)
            ).select_related("chassis__manufacturer", "chassis__location")
        )

    @staticmethod
    def get_overall_health_status() -> dict[str, Any]:
        """Get overall system health summary.

        Returns:
            Dictionary with health metrics
        """
        total_chassis = WirelessChassis.objects.count()
        online_chassis = WirelessChassis.objects.filter(is_online=True).count()
        offline_chassis = total_chassis - online_chassis

        # Count wireless units with low battery
        battery_threshold = int(25 * 255 / 100)
        low_battery_units = WirelessUnit.objects.filter(
            Q(battery__lt=battery_threshold) & ~Q(battery__isnull=True)
        ).count()

        return {
            "total_chassis": total_chassis,
            "online_chassis": online_chassis,
            "offline_chassis": offline_chassis,
            "low_battery_units": low_battery_units,
        }
