"""Authorized, deduplicated alert persistence and email delivery."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.monitoring.alert import Alert
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.models.rf_coordination.rf_channel import RFChannel
from micboard.services.monitoring.alert_fanout_dtos import AlertFanoutBudget
from micboard.services.monitoring.alert_fanout_service import AlertFanoutService
from micboard.services.notification.email import email_service
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


class AlertDeliveryService:
    """Persist and email one bounded alert after fresh authorization checks."""

    @classmethod
    def create_alert(
        cls,
        *,
        unit: WirelessUnit,
        user: Any,
        performer_assignment: PerformerAssignment,
        alert_type: str,
        message: str,
        unit_data: dict[str, Any] | None = None,
        budget: AlertFanoutBudget | None = None,
    ) -> Alert | None:
        """Create an alert when the recipient remains active, assigned, and in scope."""
        if not AlertFanoutService.recipient_has_unit_scope(unit=unit, user=user):
            logger.warning(
                "Skipped alert recipient outside device tenant: unit=%s user=%s",
                unit.pk,
                getattr(user, "pk", None),
            )
            return None

        run_budget = budget or AlertFanoutBudget.from_settings()
        if run_budget.remaining_deliveries <= 0:
            run_budget.deliveries_truncated = True
            return None
        return cls._create_scoped_alert(
            unit=unit,
            user=user,
            performer_assignment=performer_assignment,
            alert_type=alert_type,
            message=message,
            unit_data=unit_data,
            budget=run_budget,
        )

    @classmethod
    def _create_scoped_alert(
        cls,
        *,
        unit: WirelessUnit,
        user: Any,
        performer_assignment: PerformerAssignment,
        alert_type: str,
        message: str,
        unit_data: dict[str, Any] | None,
        budget: AlertFanoutBudget,
    ) -> Alert | None:
        """Serialize deduplication and revalidate immediately before persistence."""
        channel = unit.assigned_resource
        if channel is None:
            logger.warning("Cannot create %s alert for unassigned unit %s", alert_type, unit.pk)
            return None

        with transaction.atomic():
            RFChannel.objects.select_for_update().only("pk").get(pk=channel.pk)
            current_user = AlertFanoutService.current_authorized_recipient(
                unit=unit,
                assignment=performer_assignment,
                user=user,
            )
            if current_user is None:
                logger.warning(
                    "Skipped alert after recipient assignment changed: unit=%s user=%s",
                    unit.pk,
                    getattr(user, "pk", None),
                )
                return None
            if not budget.claim_delivery():
                return None

            preferences = getattr(current_user, "alert_preferences", None)
            alert_interval = max(0, int(getattr(preferences, "min_alert_interval", 5)))
            recent_alert = Alert.objects.filter(
                channel=channel,
                user=current_user,
                alert_type=alert_type,
                status__in=["pending", "sent"],
                created_at__gte=timezone.now() - timedelta(minutes=alert_interval),
            ).first()
            if recent_alert:
                logger.debug("Similar alert already exists: %s", recent_alert)
                return recent_alert

            alert = Alert.objects.create(
                channel=channel,
                user=current_user,
                assignment=performer_assignment,
                alert_type=alert_type,
                message=message,
                channel_data=unit_data or {},
            )

        logger.info("Created alert %s for user %s", alert.pk, current_user.pk)
        cls._send_email_if_allowed(
            alert=alert,
            unit=unit,
            assignment=performer_assignment,
            user=current_user,
        )
        return alert

    @staticmethod
    def _send_email_if_allowed(
        *,
        alert: Alert,
        unit: WirelessUnit,
        assignment: PerformerAssignment,
        user: Any,
    ) -> None:
        """Revalidate a recipient and deliver one already-budgeted alert email."""
        try:
            current_user = AlertFanoutService.current_authorized_recipient(
                unit=unit,
                assignment=assignment,
                user=user,
            )
            if current_user is None:
                logger.warning(
                    "Skipped alert email after recipient scope changed: alert=%s user=%s",
                    alert.pk,
                    getattr(user, "pk", None),
                )
                return
            preferences = getattr(current_user, "alert_preferences", None)
            if preferences is not None:
                if preferences.notification_method not in {"email", "both"}:
                    return
                if preferences.is_quiet_hours():
                    return
            recipient = getattr(preferences, "email_address", "") or getattr(
                current_user, "email", ""
            )
            if not recipient:
                logger.warning(
                    "Cannot dispatch alert %s: user %s has no email",
                    alert.pk,
                    current_user.pk,
                )
                return
            if not email_service.send_alert_notification(alert, recipients=[recipient]):
                alert.status = "failed"
                alert.save(update_fields=["status"])
        except Exception as exc:
            logger.exception(
                "Failed to send email for alert %s",
                alert.pk,
                exc_info=sanitized_exception_info(exc),
            )
            alert.status = "failed"
            alert.save(update_fields=["status"])
