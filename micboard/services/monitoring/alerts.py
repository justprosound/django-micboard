"""Alert management utilities for django-micboard.

Provides functions for creating and managing alerts based on device conditions.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

from django.utils import timezone

from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.monitoring.alert import Alert
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.notification.email import send_alert_email

if TYPE_CHECKING:  # pragma: no cover
    from micboard.models import PerformerAssignment as PerformerAssignmentType

logger = logging.getLogger(__name__)


class AlertManager:
    """Manages alert creation and notification based on device conditions."""

    def check_wireless_unit_alerts(self, unit: WirelessUnit) -> None:
        """Check wireless unit conditions and create alerts as needed.

        Args:
            unit: WirelessUnit instance to check
        """
        # Get active performer assignments for this unit
        assignments = PerformerAssignment.objects.filter(
            wireless_unit=unit, is_active=True
        ).select_related("performer", "monitoring_group")

        if not assignments.exists():
            return

        # Battery alerts
        self._check_battery_alerts(unit, assignments)

        # Signal loss alerts
        self._check_signal_alerts(unit, assignments)

        # Audio level alerts
        self._check_audio_alerts(unit, assignments)

    def _check_assignments_alerts(
        self,
        unit: WirelessUnit,
        assignments,
        alert_attr: str,
        condition_func: Callable[[WirelessUnit], bool],
        alert_type: str,
        message_func: Callable[[WirelessUnit], str],
    ) -> None:
        """Generic method to check alerts based on assignments and conditions.

        Args:
            unit: WirelessUnit to check
            assignments: QuerySet of PerformerAssignments
            alert_attr: Name of alert toggle attribute (e.g., 'alert_battery_low')
            condition_func: Function to check if alert condition is met
            alert_type: Type of alert to create
            message_func: Function to generate alert message
        """
        for assignment in assignments:
            if not getattr(assignment, alert_attr):
                continue

            if condition_func(unit):
                # Get users in the monitoring group
                group_users = (
                    assignment.monitoring_group.user_profiles.all()
                    if assignment.monitoring_group
                    else []
                )

                for user_profile in group_users:
                    self._create_alert(
                        unit=unit,
                        user=user_profile.user,
                        performer_assignment=assignment,
                        alert_type=alert_type,
                        message=message_func(unit),
                        unit_data=self._get_unit_snapshot(unit),
                    )

    def check_hardware_offline_alerts(self, unit: WirelessUnit) -> None:
        """Check if wireless unit is offline and create alerts.

        Args:
            unit: WirelessUnit instance to check
        """
        # Get active performer assignments with offline alerts enabled
        assignments = PerformerAssignment.objects.filter(
            wireless_unit=unit, is_active=True, alert_offline=True
        ).select_related("performer", "monitoring_group")

        # Check if unit is offline
        if unit.status != "online":
            for assignment in assignments:
                # Get users in the monitoring group
                group_users = (
                    assignment.monitoring_group.user_profiles.all()
                    if assignment.monitoring_group
                    else []
                )

                for user_profile in group_users:
                    self._create_alert(
                        unit=unit,
                        user=user_profile.user,
                        performer_assignment=assignment,
                        alert_type="hardware_offline",
                        message=f"Device offline: {unit.name}",
                        unit_data=self._get_unit_snapshot(unit),
                    )

    def _check_battery_alerts(self, unit: WirelessUnit, assignments) -> None:
        """Check battery levels and create alerts.

        Args:
            unit: WirelessUnit to check
            assignments: QuerySet of PerformerAssignments
        """
        battery_pct = unit.battery_percentage
        if battery_pct is None:
            return

        for assignment in assignments:
            if not assignment.alert_battery_low:
                continue

            # Get users in the monitoring group to notify
            group_users = (
                assignment.monitoring_group.user_profiles.all()
                if assignment.monitoring_group
                else []
            )

            for user_profile in group_users:
                user_prefs = (
                    user_profile.user.alert_preferences
                    if hasattr(user_profile.user, "alert_preferences")
                    else None
                )

                # Check critical battery level
                critical_threshold = user_prefs.battery_critical_threshold if user_prefs else 10
                if battery_pct <= critical_threshold:
                    self._create_alert(
                        unit=unit,
                        user=user_profile.user,
                        performer_assignment=assignment,
                        alert_type="battery_critical",
                        message=(
                            f"Battery critically low: {battery_pct}% - {assignment.performer.name}"
                        ),
                        unit_data=self._get_unit_snapshot(unit),
                    )
                # Check low battery level
                elif battery_pct <= (user_prefs.battery_low_threshold if user_prefs else 20):
                    self._create_alert(
                        unit=unit,
                        user=user_profile.user,
                        performer_assignment=assignment,
                        alert_type="battery_low",
                        message=f"Battery low: {battery_pct}% - {assignment.performer.name}",
                        unit_data=self._get_unit_snapshot(unit),
                    )

    def _check_signal_alerts(self, unit: WirelessUnit, assignments) -> None:
        """Check signal levels and create alerts.

        Args:
            unit: WirelessUnit to check
            assignments: QuerySet of PerformerAssignments
        """

        def signal_condition(u):
            return u.rf_level is not None and u.rf_level < -80  # dB threshold

        def signal_message(u):
            return f"Signal loss detected: RF level {u.rf_level}dB"

        self._check_assignments_alerts(
            unit,
            assignments,
            "alert_signal_loss",
            signal_condition,
            "signal_loss",
            signal_message,
        )

    def _check_audio_alerts(self, unit: WirelessUnit, assignments) -> None:
        """Check audio levels and create alerts.

        Args:
            unit: WirelessUnit to check
            assignments: QuerySet of PerformerAssignments
        """

        def audio_condition(u):
            return u.audio_level is not None and u.audio_level < -40  # dB threshold

        def audio_message(u):
            return f"Audio level too low: {u.audio_level}dB"

        self._check_assignments_alerts(
            unit,
            assignments,
            "alert_audio_low",
            audio_condition,
            "audio_low",
            audio_message,
        )

    def _create_alert(
        self,
        unit: WirelessUnit,
        user: Any,
        performer_assignment: PerformerAssignmentType,
        alert_type: str,
        message: str,
        unit_data: dict | None = None,
    ) -> Alert:
        """Create an alert if one doesn't already exist for similar conditions.

        Args:
            unit: WirelessUnit that triggered the alert
            user: User to notify
            performer_assignment: PerformerAssignment instance
            alert_type: Type of alert
            message: Alert message
            unit_data: Snapshot of unit state

        Returns:
            Alert instance (new or existing)
        """
        # Check for existing similar alert in the last hour
        recent_alert = Alert.objects.filter(
            wireless_unit=unit,
            user=user,
            alert_type=alert_type,
            status__in=["pending", "sent"],
            created_at__gte=timezone.now() - timedelta(hours=1),
        ).first()

        if recent_alert:
            logger.debug("Similar alert already exists: %s", recent_alert)
            return cast(Alert, recent_alert)

        # Create new alert
        alert = Alert.objects.create(
            wireless_unit=unit,
            user=user,
            performer_assignment=performer_assignment,
            alert_type=alert_type,
            message=message,
            unit_data=unit_data or {},
        )

        logger.info("Created alert: %s for user %s", alert, user.username)

        # Send email notification
        try:
            send_alert_email(alert)
        except Exception as e:
            logger.exception("Failed to send email for alert %s: %s", alert.id, e)
            alert.status = "failed"
            alert.save(update_fields=["status"])

        return cast(Alert, alert)

    def _get_unit_snapshot(self, unit: WirelessUnit) -> dict[str, Any]:
        """Get a snapshot of unit state for alert context."""
        snapshot = {
            "unit_name": unit.name,
            "unit_slot": unit.slot,
            "battery_percentage": unit.battery_percentage,
            "audio_level": unit.audio_level,
            "rf_level": unit.rf_level,
            "status": unit.status,
            "is_active": unit.status == "online",
            "timestamp": timezone.now().isoformat(),
        }

        # Include channel info if available
        if hasattr(unit, "channel") and unit.channel:
            snapshot.update(
                {
                    "channel_number": unit.channel.channel_number,
                    "chassis_name": unit.channel.chassis.name if unit.channel.chassis else None,
                    "chassis_ip": unit.channel.chassis.ip if unit.channel.chassis else None,
                }
            )

        return snapshot


# Global alert manager instance
alert_manager = AlertManager()


def check_transmitter_alerts(unit: WirelessUnit):
    """Convenience function to check alerts for a wireless unit.

    Args:
        unit: WirelessUnit instance
    """
    alert_manager.check_wireless_unit_alerts(unit)


def check_hardware_offline_alerts(unit: WirelessUnit):
    """Convenience function to check offline alerts for a wireless unit.

    Args:
        unit: WirelessUnit instance
    """
    alert_manager.check_hardware_offline_alerts(unit)


def acknowledge_alert(alert_id: int, user=None):
    """Acknowledge an alert (service API).

    Args:
        alert_id: Alert PK
        user: Optional user performing the acknowledgement (for audit)

    Returns:
        Updated Alert instance
    """
    alert = Alert.objects.get(id=alert_id)
    alert.status = "acknowledged"
    alert.acknowledged_at = timezone.now()
    alert.save(update_fields=["status", "acknowledged_at"])
    logger.info("Alert %s acknowledged by %s", alert.id, getattr(user, "username", None))
    return alert


def resolve_alert(alert_id: int):
    """Resolve an alert (service API).

    Args:
        alert_id: Alert PK

    Returns:
        Updated Alert instance
    """
    alert = Alert.objects.get(id=alert_id)
    alert.status = "resolved"
    alert.resolved_at = timezone.now()
    alert.save(update_fields=["status", "resolved_at"])
    logger.info("Alert %s resolved", alert.id)
    return alert
