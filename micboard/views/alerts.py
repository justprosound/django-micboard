"""Alert management utilities for django-micboard.

Provides functions for creating and managing alerts based on device conditions.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Callable, cast

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from micboard.models import Alert, PerformerAssignment, WirelessUnit
from micboard.services.email import send_alert_email

if TYPE_CHECKING:
    from micboard.models import PerformerAssignment as PerformerAssignmentType

User = get_user_model()

logger = logging.getLogger(__name__)


class AlertManager:
    """Manages alert creation and notification based on device conditions."""

    def check_unit_alerts(self, unit: WirelessUnit) -> None:
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
        """Generic method to check alerts based on assignments and conditions."""
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
        """Check if device is offline and create alerts.

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
        """Check battery levels and create alerts."""
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
        """Check signal levels and create alerts."""

        def signal_condition(u):
            return u.rf_level is not None and u.rf_level < -80  # dB threshold

        def signal_message(u):
            return f"Signal loss detected: RF level {u.rf_level}dB"

        self._check_assignments_alerts(
            unit, assignments, "alert_signal_loss", signal_condition, "signal_loss", signal_message
        )

    def _check_audio_alerts(self, unit: WirelessUnit, assignments) -> None:
        """Check audio levels and create alerts."""

        def audio_condition(u):
            return u.audio_level is not None and u.audio_level < -40  # dB threshold

        def audio_message(u):
            return f"Audio level too low: {u.audio_level}dB"

        self._check_assignments_alerts(
            unit, assignments, "alert_on_audio_low", audio_condition, "audio_low", audio_message
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
        """Create an alert if one doesn't already exist for similar conditions."""
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


def check_unit_alerts(unit):
    """Convenience function to check alerts for a unit."""
    alert_manager.check_unit_alerts(unit)


def check_hardware_offline_alerts(unit):
    """Convenience function to check offline alerts for a channel."""
    alert_manager.check_hardware_offline_alerts(unit)


@login_required
@require_http_methods(["GET"])
def alerts_view(request: HttpRequest) -> HttpResponse:
    """View to display and manage system alerts."""
    status_filter = request.GET.get("status", "pending")
    alert_type_filter = request.GET.get("type", "")
    page_number = request.GET.get("page", 1)

    # Base queryset
    alerts = Alert.objects.select_related("channel", "user").order_by("-created_at")

    # Apply filters
    if status_filter and status_filter != "all":
        alerts = alerts.filter(status=status_filter)
    if alert_type_filter:
        alerts = alerts.filter(alert_type=alert_type_filter)

    # Paginate results
    paginator = Paginator(alerts, 25)  # 25 alerts per page
    page_obj = paginator.get_page(page_number)

    # Alert statistics
    stats = {
        "total": Alert.objects.count(),
        "pending": Alert.objects.filter(status="pending").count(),
        "acknowledged": Alert.objects.filter(status="acknowledged").count(),
        "resolved": Alert.objects.filter(status="resolved").count(),
        "failed": Alert.objects.filter(status="failed").count(),
    }

    context = {
        "alerts": page_obj,
        "stats": stats,
        "status_filter": status_filter,
        "alert_type_filter": alert_type_filter,
        "alert_types": Alert.ALERT_TYPES,
        "alert_statuses": Alert.ALERT_STATUS,
    }
    return render(request, "micboard/alerts.html", context)


@login_required
@require_http_methods(["GET"])
def alert_detail_view(request: HttpRequest, alert_id: int) -> HttpResponse:
    """View to display detailed information about a specific alert."""
    alert = get_object_or_404(Alert.objects.select_related("channel", "user"), id=alert_id)

    context = {
        "alert": alert,
    }
    return render(request, "micboard/alert_detail.html", context)


@login_required
@require_http_methods(["POST"])
def acknowledge_alert_view(request: HttpRequest, alert_id: int) -> HttpResponse:
    """View to acknowledge an alert."""
    alert = get_object_or_404(Alert, id=alert_id)
    alert.acknowledge(request.user)
    messages.success(request, f"Alert '{alert}' has been acknowledged.")
    return redirect(request.headers.get("referer") or "alerts")


@login_required
@require_http_methods(["POST"])
def resolve_alert_view(request: HttpRequest, alert_id: int) -> HttpResponse:
    """View to resolve an alert."""
    alert = get_object_or_404(Alert, id=alert_id)
    alert.resolve()
    messages.success(request, f"Alert '{alert}' has been resolved.")
    return redirect(request.headers.get("referer") or "alerts")
