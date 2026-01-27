"""Performer assignment service for managing performer-to-unit assignments.

Handles performer lifecycle, device assignment, and monitor group context.
This is the recommended pattern for modern deployments (vs legacy DeviceAssignment).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from django.db import models
from django.db.models import QuerySet

from micboard.models import PerformerAssignment, WirelessUnit
from micboard.services.exceptions import HardwareNotFoundError

if TYPE_CHECKING:
    from django.contrib.auth.models import User

    from micboard.models import MonitoringGroup, Performer

_ModelT = TypeVar("_ModelT", bound=models.Model)


class PerformerAssignmentService:
    """Business logic for performer-to-unit assignments and alert management."""

    @staticmethod
    def create_assignment(
        *,
        performer: Performer,
        wireless_unit: WirelessUnit,
        monitoring_group: MonitoringGroup,
        priority: str = "normal",
        alert_enabled: bool = True,
        notes: str = "",
        assigned_by: User | None = None,
    ) -> PerformerAssignment:
        """Create a new performer-to-unit assignment.

        Args:
            performer: Performer to assign.
            wireless_unit: WirelessUnit to assign performer to.
            monitoring_group: MonitoringGroup managing this assignment.
            priority: Priority level (low, normal, high, critical).
            alert_enabled: Whether alerts are enabled for this assignment.
            notes: Optional assignment notes.
            assigned_by: User (tech/admin) who created the assignment.

        Returns:
            Created PerformerAssignment.

        Raises:
            HardwareNotFoundError: If wireless_unit doesn't exist.
        """
        if not wireless_unit:
            raise HardwareNotFoundError(message="WirelessUnit not found")

        # If already exists, return it
        assignment, created = PerformerAssignment.objects.get_or_create(
            performer=performer,
            wireless_unit=wireless_unit,
            defaults={
                "monitoring_group": monitoring_group,
                "priority": priority,
                "alert_on_battery_low": alert_enabled,
                "alert_on_signal_loss": alert_enabled,
                "alert_on_hardware_offline": alert_enabled,
                "notes": notes,
                "assigned_by": assigned_by,
            },
        )

        return assignment

    @staticmethod
    def update_assignment(
        *,
        assignment: PerformerAssignment,
        priority: str | None = None,
        alert_enabled: bool | None = None,
        notes: str | None = None,
    ) -> PerformerAssignment:
        """Update alert flags or notes on an assignment.

        Args:
            assignment: PerformerAssignment to update.
            priority: New priority level or None to skip.
            alert_enabled: New alert state or None to skip.
            notes: New notes or None to skip.

        Returns:
            Updated PerformerAssignment.
        """
        updated_fields: list[str] = []

        if priority is not None and assignment.priority != priority:
            assignment.priority = priority
            updated_fields.append("priority")

        if alert_enabled is not None:
            if assignment.alert_on_battery_low != alert_enabled:
                assignment.alert_on_battery_low = alert_enabled
                updated_fields.append("alert_on_battery_low")
            if assignment.alert_on_signal_loss != alert_enabled:
                assignment.alert_on_signal_loss = alert_enabled
                updated_fields.append("alert_on_signal_loss")
            if assignment.alert_on_hardware_offline != alert_enabled:
                assignment.alert_on_hardware_offline = alert_enabled
                updated_fields.append("alert_on_hardware_offline")

        if notes is not None and assignment.notes != notes:
            assignment.notes = notes
            updated_fields.append("notes")

        if updated_fields:
            assignment.save(update_fields=updated_fields)

        return assignment

    @staticmethod
    def delete_assignment(*, assignment: PerformerAssignment) -> None:
        """Soft-delete or hard-delete an assignment.

        Args:
            assignment: PerformerAssignment to delete.
        """
        # Current implementation uses hard delete, could be soft-delete
        # by setting is_active=False if retention is needed
        assignment.delete()

    @staticmethod
    def get_performer_assignments(*, performer: Performer | int) -> QuerySet[PerformerAssignment]:
        """Get all assignments for a performer with optimization.

        Args:
            performer: Performer instance or ID.

        Returns:
            QuerySet of active assignments with related objects prefetched.
        """
        if isinstance(performer, int):
            performer_id = performer
        else:
            performer_id = performer.id

        return PerformerAssignment.objects.filter(
            performer_id=performer_id, is_active=True
        ).with_performer_and_unit()

    @staticmethod
    def get_unit_assignments(*, wireless_unit: WirelessUnit | int) -> QuerySet[PerformerAssignment]:
        """Get all assignments for a wireless unit.

        Args:
            wireless_unit: WirelessUnit instance or ID.

        Returns:
            QuerySet of active assignments.
        """
        if isinstance(wireless_unit, int):
            unit_id = wireless_unit
        else:
            unit_id = wireless_unit.id

        return PerformerAssignment.objects.filter(
            wireless_unit_id=unit_id, is_active=True
        ).with_performer_and_unit()

    @staticmethod
    def get_group_assignments(
        *, monitoring_group: MonitoringGroup | int
    ) -> QuerySet[PerformerAssignment]:
        """Get all assignments managed by a monitoring group.

        Args:
            monitoring_group: MonitoringGroup instance or ID.

        Returns:
            QuerySet of active assignments in the group.
        """
        if isinstance(monitoring_group, int):
            group_id = monitoring_group
        else:
            group_id = monitoring_group.id

        return PerformerAssignment.objects.filter(
            monitoring_group_id=group_id, is_active=True
        ).with_performer_and_unit()

    @staticmethod
    def get_assignments_needing_alerts(
        *,
        monitoring_group: MonitoringGroup | None = None,
        after=None,
    ) -> QuerySet[PerformerAssignment]:
        """Get assignments with alerts enabled.

        Args:
            monitoring_group: Optional group to filter by.
            after: Optional datetime to filter by last update.

        Returns:
            QuerySet of assignments needing alert monitoring.
        """
        qs = PerformerAssignment.objects.needing_alerts(after=after)

        if monitoring_group:
            if isinstance(monitoring_group, int):
                qs = qs.filter(monitoring_group_id=monitoring_group)
            else:
                qs = qs.filter(monitoring_group=monitoring_group)

        return qs.with_performer_and_unit()

    @staticmethod
    def update_alert_status(
        *,
        assignment: PerformerAssignment,
        alert_enabled: bool,
    ) -> PerformerAssignment:
        """Update alert status for an assignment.

        Args:
            assignment: PerformerAssignment to update.
            alert_enabled: New alert state.

        Returns:
            Updated assignment.
        """
        return PerformerAssignmentService.update_assignment(
            assignment=assignment, alert_enabled=alert_enabled
        )

    @staticmethod
    def count_total_assignments() -> int:
        """Count total number of active performer assignments.

        Returns:
            Total count.
        """
        return PerformerAssignment.objects.filter(is_active=True).count()

    @staticmethod
    def count_assignments_with_alerts() -> int:
        """Count assignments with any alerts enabled.

        Returns:
            Count of assignments with alerts.
        """
        return (
            PerformerAssignment.objects.filter(
                is_active=True,
            )
            .exclude(
                alert_on_battery_low=False,
                alert_on_signal_loss=False,
                alert_on_hardware_offline=False,
                alert_on_audio_low=False,
            )
            .count()
        )

    @staticmethod
    def deactivate_assignment(*, assignment: PerformerAssignment) -> PerformerAssignment:
        """Soft-deactivate an assignment without deleting.

        Args:
            assignment: PerformerAssignment to deactivate.

        Returns:
            Updated assignment.
        """
        assignment.is_active = False
        assignment.save(update_fields=["is_active"])
        return assignment

    @staticmethod
    def reactivate_assignment(*, assignment: PerformerAssignment) -> PerformerAssignment:
        """Reactivate a deactivated assignment.

        Args:
            assignment: PerformerAssignment to reactivate.

        Returns:
            Updated assignment.
        """
        assignment.is_active = True
        assignment.save(update_fields=["is_active"])
        return assignment
