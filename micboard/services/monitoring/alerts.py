"""Alert management utilities for django-micboard.

Provides functions for creating and managing alerts based on device conditions.
"""

from __future__ import annotations

import logging
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
from micboard.services.monitoring.alert_delivery_service import AlertDeliveryService
from micboard.services.monitoring.alert_fanout_dtos import AlertFanoutBudget
from micboard.services.monitoring.alert_fanout_service import AlertFanoutService

logger = logging.getLogger(__name__)


def get_alerts_for_user(user: User | AnonymousUser) -> QuerySet[Alert]:
    """Return recipient-private alerts within the user's tenant boundary."""
    if not user.is_authenticated or not getattr(user, "is_active", False):
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

    def check_wireless_unit_alerts(
        self,
        unit: WirelessUnit,
        *,
        budget: AlertFanoutBudget | None = None,
    ) -> None:
        """Check wireless unit conditions and create alerts as needed.

        Args:
            unit: WirelessUnit instance to check
        """
        run_budget = budget or AlertFanoutBudget.from_settings()
        battery_pct = get_battery_percentage(unit)
        signal_loss = unit.rf_level is not None and unit.rf_level < -80
        audio_low = unit.audio_level is not None and unit.audio_level < -40
        if battery_pct is None and not signal_loss and not audio_low:
            return

        assignments = AlertFanoutService.assignments_for_unit(
            unit=unit,
            scope="transmitter",
            budget=run_budget,
        )
        recipients_by_assignment = AlertFanoutService.recipients_for_assignments(
            unit=unit,
            assignments=assignments,
            scope="transmitter",
            budget=run_budget,
        )
        snapshot = self._get_unit_snapshot(unit)
        for assignment in assignments:
            for user in recipients_by_assignment.get(assignment.pk, []):
                for alert_type, message in self._transmitter_alerts_for_recipient(
                    unit=unit,
                    assignment=assignment,
                    user=user,
                    battery_pct=battery_pct,
                    signal_loss=signal_loss,
                    audio_low=audio_low,
                ):
                    AlertDeliveryService.create_alert(
                        unit=unit,
                        user=user,
                        performer_assignment=assignment,
                        alert_type=alert_type,
                        message=message,
                        unit_data=snapshot,
                        budget=run_budget,
                    )

    def check_hardware_offline_alerts(
        self,
        unit: WirelessUnit,
        *,
        budget: AlertFanoutBudget | None = None,
    ) -> None:
        """Check if wireless unit is offline and create alerts.

        Args:
            unit: WirelessUnit instance to check
        """
        if unit.status == "online":
            return

        run_budget = budget or AlertFanoutBudget.from_settings()
        assignments = AlertFanoutService.assignments_for_unit(
            unit=unit,
            scope="offline",
            budget=run_budget,
            offline_only=True,
        )
        recipients_by_assignment = AlertFanoutService.recipients_for_assignments(
            unit=unit,
            assignments=assignments,
            scope="offline",
            budget=run_budget,
        )
        snapshot = self._get_unit_snapshot(unit)
        for assignment in assignments:
            for user in recipients_by_assignment.get(assignment.pk, []):
                AlertDeliveryService.create_alert(
                    unit=unit,
                    user=user,
                    performer_assignment=assignment,
                    alert_type="hardware_offline",
                    message=f"Device offline: {unit.name}",
                    unit_data=snapshot,
                    budget=run_budget,
                )

    @staticmethod
    def _transmitter_alerts_for_recipient(
        *,
        unit: WirelessUnit,
        assignment: PerformerAssignment,
        user: Any,
        battery_pct: int | None,
        signal_loss: bool,
        audio_low: bool,
    ) -> list[tuple[str, str]]:
        """Build enabled transmitter alert candidates for one bounded recipient."""
        candidates: list[tuple[str, str]] = []
        preferences = getattr(user, "alert_preferences", None)
        if assignment.alert_on_battery_low and battery_pct is not None:
            critical_threshold = getattr(preferences, "battery_critical_threshold", 10)
            low_threshold = getattr(preferences, "battery_low_threshold", 20)
            if battery_pct <= critical_threshold:
                candidates.append(
                    (
                        "battery_critical",
                        f"Battery critically low: {battery_pct}% - {assignment.performer.name}",
                    )
                )
            elif battery_pct <= low_threshold:
                candidates.append(
                    (
                        "battery_low",
                        f"Battery low: {battery_pct}% - {assignment.performer.name}",
                    )
                )
        if assignment.alert_on_signal_loss and signal_loss:
            candidates.append(("signal_loss", f"Signal loss detected: RF level {unit.rf_level}dB"))
        if assignment.alert_on_audio_low and audio_low:
            candidates.append(("audio_low", f"Audio level too low: {unit.audio_level}dB"))
        return candidates

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


def check_transmitter_alerts(
    unit: WirelessUnit,
    *,
    budget: AlertFanoutBudget | None = None,
) -> None:
    """Convenience function to check alerts for a wireless unit.

    Args:
        unit: WirelessUnit instance
    """
    if budget is None:
        alert_manager.check_wireless_unit_alerts(unit)
    else:
        alert_manager.check_wireless_unit_alerts(unit, budget=budget)


def check_hardware_offline_alerts(
    unit: WirelessUnit,
    *,
    budget: AlertFanoutBudget | None = None,
) -> None:
    """Convenience function to check offline alerts for a wireless unit.

    Args:
        unit: WirelessUnit instance
    """
    if budget is None:
        alert_manager.check_hardware_offline_alerts(unit)
    else:
        alert_manager.check_hardware_offline_alerts(unit, budget=budget)


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
    logger.info("Alert %s acknowledged by user %s", alert.id, getattr(user, "pk", None))
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
    logger.info("Alert %s resolved by user %s", alert.id, getattr(user, "pk", None))
    return alert
