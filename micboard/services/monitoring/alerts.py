"""Alert management utilities for django-micboard.

Provides functions for creating and managing alerts based on device conditions.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from django.contrib.auth.models import AnonymousUser, User
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from micboard.models.base_managers import TenantOptimizedQuerySet
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.monitoring.alert import Alert
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.hardware.wireless_unit_service import get_battery_percentage
from micboard.services.notification.email import send_alert_email

logger = logging.getLogger(__name__)


def get_alerts_for_user(user: User | AnonymousUser) -> QuerySet[Alert]:
    """Return recipient-private alerts within the user's tenant boundary."""
    if not user.is_authenticated:
        return Alert.objects.none()

    tenant_alerts: QuerySet[Alert] = TenantOptimizedQuerySet(
        Alert,
        using=Alert.objects.db,
    ).for_user(user=user)
    if user.is_superuser:
        return tenant_alerts
    return tenant_alerts.filter(user_id=user.pk)


class AlertManager:
    """Manages alert creation and notification based on device conditions."""

    def check_wireless_unit_alerts(self, unit: WirelessUnit) -> None:
        """Check wireless unit conditions and create alerts as needed.

        Args:
            unit: WirelessUnit instance to check
        """
        # Get active performer assignments for this unit
        assignments = list(
            PerformerAssignment.objects.filter(wireless_unit=unit, is_active=True)
            .select_related("performer", "monitoring_group")
            .prefetch_related("monitoring_group__users__alert_preferences")
        )

        if not assignments:
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
            alert_attr: Name of alert toggle attribute (e.g., ``alert_on_battery_low``)
            condition_func: Function to check if alert condition is met
            alert_type: Type of alert to create
            message_func: Function to generate alert message
        """
        for assignment in assignments:
            if not getattr(assignment, alert_attr):
                continue

            if condition_func(unit):
                # Get users in the monitoring group
                group_users = assignment.monitoring_group.users.all()

                for user in group_users:
                    self._create_alert(
                        unit=unit,
                        user=user,
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
        if unit.status == "online":
            return

        assignments = list(
            PerformerAssignment.objects.filter(
                wireless_unit=unit,
                is_active=True,
                alert_on_hardware_offline=True,
            )
            .select_related("performer", "monitoring_group")
            .prefetch_related("monitoring_group__users")
        )
        for assignment in assignments:
            for user in assignment.monitoring_group.users.all():
                self._create_alert(
                    unit=unit,
                    user=user,
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
        battery_pct = get_battery_percentage(unit)
        if battery_pct is None:
            return

        for assignment in assignments:
            if not assignment.alert_on_battery_low:
                continue

            # Get users in the monitoring group to notify
            group_users = assignment.monitoring_group.users.all()

            for user in group_users:
                user_prefs = user.alert_preferences if hasattr(user, "alert_preferences") else None

                # Check critical battery level
                critical_threshold = user_prefs.battery_critical_threshold if user_prefs else 10
                if battery_pct <= critical_threshold:
                    self._create_alert(
                        unit=unit,
                        user=user,
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
                        user=user,
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
            "alert_on_signal_loss",
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
            "alert_on_audio_low",
            audio_condition,
            "audio_low",
            audio_message,
        )

    def _create_alert(
        self,
        unit: WirelessUnit,
        user: Any,
        performer_assignment: PerformerAssignment,
        alert_type: str,
        message: str,
        unit_data: dict | None = None,
    ) -> Alert | None:
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
        channel = unit.assigned_resource
        if channel is None:
            logger.warning("Cannot create %s alert for unassigned unit %s", alert_type, unit.pk)
            return None

        recent_alert = Alert.objects.filter(
            channel=channel,
            user=user,
            alert_type=alert_type,
            status__in=["pending", "sent"],
            created_at__gte=timezone.now() - timedelta(hours=1),
        ).first()

        if recent_alert:
            logger.debug("Similar alert already exists: %s", recent_alert)
            return recent_alert

        # Create new alert
        alert = Alert.objects.create(
            channel=channel,
            user=user,
            assignment=performer_assignment,
            alert_type=alert_type,
            message=message,
            channel_data=unit_data or {},
        )

        logger.info("Created alert: %s for user %s", alert, user.username)

        # Send email notification
        try:
            send_alert_email(alert)
        except Exception as e:
            logger.exception("Failed to send email for alert %s: %s", alert.id, e)
            alert.status = "failed"
            alert.save(update_fields=["status"])

        return alert

    def _get_unit_snapshot(self, unit: WirelessUnit) -> dict[str, Any]:
        """Get a snapshot of unit state for alert context."""
        snapshot = {
            "unit_name": unit.name,
            "unit_slot": unit.slot,
            "battery_percentage": get_battery_percentage(unit),
            "audio_level": unit.audio_level,
            "rf_level": unit.rf_level,
            "status": unit.status,
            "is_active": unit.status == "online",
            "timestamp": timezone.now().isoformat(),
        }

        # Include channel info if available
        if unit.assigned_resource:
            channel = unit.assigned_resource
            snapshot.update(
                {
                    "channel_number": channel.channel_number,
                    "chassis_name": channel.chassis.name,
                    "chassis_ip": channel.chassis.ip,
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


@transaction.atomic
def acknowledge_alert(alert_id: int, *, user: User | AnonymousUser) -> Alert:
    """Acknowledge an alert (service API).

    Args:
        alert_id: Alert PK
        user: User performing the acknowledgement.

    Returns:
        Updated Alert instance
    """
    alert = get_alerts_for_user(user).select_for_update().get(id=alert_id)
    if alert.status == "acknowledged":
        return alert
    if alert.status != "pending":
        raise ValueError("Only pending alerts can be acknowledged")

    alert.status = "acknowledged"
    alert.acknowledged_at = timezone.now()
    alert.save(update_fields=["status", "acknowledged_at"])
    logger.info("Alert %s acknowledged by %s", alert.id, getattr(user, "username", None))
    return alert


@transaction.atomic
def resolve_alert(alert_id: int, *, user: User | AnonymousUser) -> Alert:
    """Resolve an alert (service API).

    Args:
        alert_id: Alert PK
        user: User performing the resolution.

    Returns:
        Updated Alert instance
    """
    alert = get_alerts_for_user(user).select_for_update().get(id=alert_id)
    if alert.status == "resolved":
        return alert
    if alert.status not in {"pending", "acknowledged"}:
        raise ValueError("Only pending or acknowledged alerts can be resolved")

    alert.status = "resolved"
    alert.resolved_at = timezone.now()
    alert.save(update_fields=["status", "resolved_at"])
    logger.info("Alert %s resolved by %s", alert.id, getattr(user, "username", None))
    return alert
