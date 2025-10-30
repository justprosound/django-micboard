"""
Alert management utilities for django-micboard.

Provides functions for creating and managing alerts based on device conditions.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Callable, cast

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from micboard.models import Alert
from micboard.services.email import send_alert_email

if TYPE_CHECKING:
    from micboard.models import Channel, DeviceAssignment, Transmitter

User = get_user_model()

logger = logging.getLogger(__name__)


class AlertManager:
    """
    Manages alert creation and notification based on device conditions.
    """

    def check_transmitter_alerts(self, transmitter: Transmitter) -> None:
        """
        Check transmitter conditions and create alerts as needed.

        Args:
            transmitter: Transmitter instance to check
        """
        # Battery alerts
        self._check_battery_alerts(transmitter)

        # Signal loss alerts
        self._check_signal_alerts(transmitter)

        # Audio level alerts
        self._check_audio_alerts(transmitter)

    def _check_assignments_alerts(
        self,
        transmitter: Transmitter,
        alert_attr: str,
        condition_func: Callable[[Transmitter], bool],
        alert_type: str,
        message_func: Callable[[Transmitter], str],
    ) -> None:
        """Generic method to check alerts based on assignments and conditions."""
        assignments = transmitter.channel.assignments.filter(is_active=True)

        for assignment in assignments:
            if not getattr(assignment, alert_attr):
                continue

            if condition_func(transmitter):
                self._create_alert(
                    channel=transmitter.channel,
                    user=assignment.user,
                    assignment=assignment,
                    alert_type=alert_type,
                    message=message_func(transmitter),
                    channel_data=self._get_channel_snapshot(transmitter.channel),
                )

    def check_device_offline_alerts(self, channel: Channel) -> None:
        """
        Check if device/channel is offline and create alerts.

        Args:
            channel: Channel instance to check
        """
        # Check if receiver is offline
        if not channel.receiver.is_active:
            self._create_device_offline_alert(channel)
        else:
            # Check if transmitter is offline (no recent updates)
            if hasattr(channel, "transmitter"):
                transmitter = channel.transmitter
                if not transmitter.is_active:
                    self._create_device_offline_alert(channel)

    def _check_battery_alerts(self, transmitter: Transmitter) -> None:
        """Check battery levels and create alerts."""
        battery_pct = transmitter.battery_percentage
        if battery_pct is None:
            return

        # Get assignments for this channel
        assignments = transmitter.channel.assignments.filter(is_active=True)

        for assignment in assignments:
            if not assignment.alert_on_battery_low:
                continue

            user_prefs = (
                assignment.user.alert_preferences
                if hasattr(assignment.user, "alert_preferences")
                else None
            )

            # Check critical battery level
            critical_threshold = user_prefs.battery_critical_threshold if user_prefs else 10
            if battery_pct <= critical_threshold:
                self._create_alert(
                    channel=transmitter.channel,
                    user=assignment.user,
                    assignment=assignment,
                    alert_type="battery_critical",
                    message=f"Battery critically low: {battery_pct}%",
                    channel_data=self._get_channel_snapshot(transmitter.channel),
                )
            # Check low battery level
            elif battery_pct <= (user_prefs.battery_low_threshold if user_prefs else 20):
                self._create_alert(
                    channel=transmitter.channel,
                    user=assignment.user,
                    assignment=assignment,
                    alert_type="battery_low",
                    message=f"Battery low: {battery_pct}%",
                    channel_data=self._get_channel_snapshot(transmitter.channel),
                )

    def _check_signal_alerts(self, transmitter: Transmitter) -> None:
        """Check signal levels and create alerts."""

        def signal_condition(tx):
            return tx.rf_level < -80  # dB threshold

        def signal_message(tx):
            return f"Signal loss detected: RF level {tx.rf_level}dB"

        self._check_assignments_alerts(
            transmitter, "alert_on_signal_loss", signal_condition, "signal_loss", signal_message
        )

    def _check_audio_alerts(self, transmitter: Transmitter) -> None:
        """Check audio levels and create alerts."""

        def audio_condition(tx):
            return tx.audio_level < -40  # dB threshold

        def audio_message(tx):
            return f"Audio level too low: {tx.audio_level}dB"

        self._check_assignments_alerts(
            transmitter, "alert_on_audio_low", audio_condition, "audio_low", audio_message
        )

    def _create_device_offline_alert(self, channel: Channel) -> None:
        """Create device offline alerts for all assignments."""
        assignments = channel.assignments.filter(is_active=True, alert_on_device_offline=True)

        for assignment in assignments:
            self._create_alert(
                channel=channel,
                user=assignment.user,
                assignment=assignment,
                alert_type="device_offline",
                message=f"Device offline: {channel.receiver.name} Channel {channel.channel_number}",
                channel_data=self._get_channel_snapshot(channel),
            )

    def _create_alert(
        self,
        channel: Channel,
        user: Any,
        assignment: DeviceAssignment,
        alert_type: str,
        message: str,
        channel_data: dict | None = None,
    ) -> Alert:
        """
        Create an alert if one doesn't already exist for similar conditions.

        Args:
            channel: Channel that triggered the alert
            user: User to notify
            assignment: Device assignment
            alert_type: Type of alert
            message: Alert message
            channel_data: Snapshot of channel state

        Returns:
            Alert instance (new or existing)
        """
        from micboard.models import Alert

        # Check for existing similar alert in the last hour
        recent_alert = Alert.objects.filter(
            channel=channel,
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
            channel=channel,
            user=user,
            assignment=assignment,
            alert_type=alert_type,
            message=message,
            channel_data=channel_data or {},
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

    def _get_channel_snapshot(self, channel: Channel) -> dict[str, Any]:
        """Get a snapshot of channel state for alert context."""
        snapshot = {
            "receiver_name": channel.receiver.name,
            "receiver_ip": channel.receiver.ip,
            "receiver_is_active": channel.receiver.is_active,
            "channel_number": channel.channel_number,
            "timestamp": timezone.now().isoformat(),
        }

        if hasattr(channel, "transmitter"):
            transmitter = channel.transmitter
            snapshot.update(
                {
                    "transmitter_name": transmitter.name,
                    "transmitter_slot": transmitter.slot,
                    "battery_percentage": transmitter.battery_percentage,
                    "audio_level": transmitter.audio_level,
                    "rf_level": transmitter.rf_level,
                    "status": transmitter.status,
                    "is_active": transmitter.is_active,
                }
            )

        return snapshot


# Global alert manager instance
alert_manager = AlertManager()


def check_transmitter_alerts(transmitter):
    """
    Convenience function to check alerts for a transmitter.

    Args:
        transmitter: Transmitter instance
    """
    alert_manager.check_transmitter_alerts(transmitter)


def check_device_offline_alerts(channel):
    """
    Convenience function to check offline alerts for a channel.

    Args:
        channel: Channel instance
    """
    alert_manager.check_device_offline_alerts(channel)


def alerts_view(request: HttpRequest) -> HttpResponse:
    """View to display and manage system alerts"""
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


def alert_detail_view(request: HttpRequest, alert_id: int) -> HttpResponse:
    """
    View to display detailed information about a specific alert
    """
    alert = get_object_or_404(Alert.objects.select_related("channel", "user"), id=alert_id)

    context = {
        "alert": alert,
    }
    return render(request, "micboard/alert_detail.html", context)


def acknowledge_alert_view(request: HttpRequest, alert_id: int) -> HttpResponse:
    """
    View to acknowledge an alert
    """
    if request.method != "POST":
        return redirect("alert_detail", alert_id=alert_id)

    alert = get_object_or_404(Alert, id=alert_id)
    alert.acknowledge(request.user if request.user.is_authenticated else None)
    messages.success(request, f"Alert '{alert}' has been acknowledged.")
    return redirect(request.META.get("HTTP_REFERER") or "alerts")


def resolve_alert_view(request: HttpRequest, alert_id: int) -> HttpResponse:
    """
    View to resolve an alert
    """
    if request.method != "POST":
        return redirect("alert_detail", alert_id=alert_id)

    alert = get_object_or_404(Alert, id=alert_id)
    alert.resolve()
    messages.success(request, f"Alert '{alert}' has been resolved.")
    return redirect(request.META.get("HTTP_REFERER") or "alerts")
