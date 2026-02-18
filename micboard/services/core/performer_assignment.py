"""Performer assignment service layer for binding devices to performers.

Handles assignment lifecycle, state transitions, and lookup helpers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db.models import QuerySet

from micboard.models.monitoring.performer_assignment import PerformerAssignment

if TYPE_CHECKING:  # pragma: no cover
    from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


class PerformerAssignmentService:
    """Business logic for performer-to-device assignments."""

    @staticmethod
    def get_active_assignments() -> QuerySet[PerformerAssignment]:
        """Get all active performer assignments with related data."""
        return (
            PerformerAssignment.objects.filter(is_active=True)
            .select_related(
                "performer",
                "wireless_unit",
                "wireless_unit__base_chassis",
                "monitoring_group",
            )
            .order_by("-priority", "performer__name")
        )

    @staticmethod
    def create_assignment(
        *,
        performer_id: int,
        unit_id: int,
        group_id: int,
        priority: str = "normal",
        notes: str | None = None,
        alert_on_battery_low: bool | None = None,
        alert_on_signal_loss: bool | None = None,
        alert_on_audio_low: bool | None = None,
        alert_on_hardware_offline: bool | None = None,
        is_active: bool = True,
        user: User | None = None,
    ) -> PerformerAssignment:
        """Create a new performer assignment with optional alert preferences.

        Backwards-compatible: callers that previously passed the smaller set of
        arguments will continue to work.
        """
        from django.db import transaction

        with transaction.atomic():
            assignment = PerformerAssignment.objects.create(
                performer_id=performer_id,
                wireless_unit_id=unit_id,
                monitoring_group_id=group_id,
                priority=priority,
                notes=notes or "",
                alert_on_battery_low=bool(alert_on_battery_low)
                if alert_on_battery_low is not None
                else False,
                alert_on_signal_loss=bool(alert_on_signal_loss)
                if alert_on_signal_loss is not None
                else False,
                alert_on_audio_low=bool(alert_on_audio_low)
                if alert_on_audio_low is not None
                else False,
                alert_on_hardware_offline=bool(alert_on_hardware_offline)
                if alert_on_hardware_offline is not None
                else False,
                is_active=is_active,
                assigned_by=user,
            )

            # TODO: emit audit log / signals if required by calling code
            return assignment

    @staticmethod
    def update_assignment(
        *,
        assignment_id: int,
        priority: str | None = None,
        notes: str | None = None,
        is_active: bool | None = None,
        alert_on_battery_low: bool | None = None,
        alert_on_signal_loss: bool | None = None,
        alert_on_audio_low: bool | None = None,
        alert_on_hardware_offline: bool | None = None,
    ) -> PerformerAssignment:
        """Update fields on an existing assignment and return the instance.

        Raises PerformerAssignment.DoesNotExist if the assignment is missing.
        """
        from django.db import transaction

        with transaction.atomic():
            assignment = PerformerAssignment.objects.select_for_update().get(id=assignment_id)

            if priority is not None:
                assignment.priority = priority
            if notes is not None:
                assignment.notes = notes
            if is_active is not None:
                assignment.is_active = is_active
            if alert_on_battery_low is not None:
                assignment.alert_on_battery_low = alert_on_battery_low
            if alert_on_signal_loss is not None:
                assignment.alert_on_signal_loss = alert_on_signal_loss
            if alert_on_audio_low is not None:
                assignment.alert_on_audio_low = alert_on_audio_low
            if alert_on_hardware_offline is not None:
                assignment.alert_on_hardware_offline = alert_on_hardware_offline

            assignment.save()
            return assignment

    @staticmethod
    def delete_assignment(*, assignment_id: int) -> bool:
        """Permanently delete an assignment. Returns True if deleted, False if not found."""
        try:
            assignment = PerformerAssignment.objects.get(id=assignment_id)
            assignment.delete()
            return True
        except PerformerAssignment.DoesNotExist:
            return False

    @staticmethod
    def deactivate_assignment(*, assignment_id: int) -> bool:
        """Deactivate an existing assignment."""
        try:
            assignment = PerformerAssignment.objects.get(id=assignment_id)
            assignment.is_active = False
            assignment.save(update_fields=["is_active", "updated_at"])
            return True
        except PerformerAssignment.DoesNotExist:
            return False
