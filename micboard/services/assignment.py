"""Assignment service layer for managing user-channel assignments.

Handles assignment lifecycle, alert preferences, and notification logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import QuerySet

from micboard.models import Assignment, RFChannel, WirelessChassis
from micboard.services.exceptions import AssignmentAlreadyExistsError, DeviceNotFoundError

if TYPE_CHECKING:
    from django.contrib.auth.models import User


class AssignmentService:
    """Business logic for user-channel assignments and alert management."""

    @staticmethod
    def create_assignment(
        *,
        user: User,
        channel: RFChannel | int | None = None,
        device: WirelessChassis | None = None,
        alert_enabled: bool = True,
        notes: str = "",
    ) -> Assignment:
        """Create a new user assignment for a channel.

        Accepts either an RFChannel instance/ID or a WirelessChassis (fallback uses first channel).
        """
        channel_obj: RFChannel | None = None
        if isinstance(channel, int):
            channel_obj = RFChannel.objects.filter(id=channel).first()
        elif isinstance(channel, RFChannel):
            channel_obj = channel

        if channel_obj is None and device is not None:
            channel_obj = device.rf_channels.first()

        if channel_obj is None:
            raise DeviceNotFoundError(message="No channel available for assignment")

        if Assignment.objects.filter(user=user, channel=channel_obj).exists():
            raise AssignmentAlreadyExistsError(user_id=user.id, channel_id=channel_obj.id)

        return Assignment.objects.create(
            user=user,
            channel=channel_obj,
            notes=notes,
            alert_on_device_offline=alert_enabled,
        )

    @staticmethod
    def update_assignment(
        *, assignment: Assignment, alert_enabled: bool | None = None, notes: str | None = None
    ) -> Assignment:
        """Update alert flags or notes on an assignment."""
        updated_fields: list[str] = []

        if alert_enabled is not None and assignment.alert_on_device_offline != alert_enabled:
            assignment.alert_on_device_offline = alert_enabled
            updated_fields.append("alert_on_device_offline")

        if notes is not None and assignment.notes != notes:
            assignment.notes = notes
            updated_fields.append("notes")

        if updated_fields:
            assignment.save(update_fields=updated_fields)

        return assignment

    @staticmethod
    def delete_assignment(*, assignment: Assignment) -> None:
        """Delete an assignment.

        Args:
            assignment: Assignment instance to delete.
        """
        assignment.delete()

    @staticmethod
    def get_user_assignments(*, user: User | int) -> QuerySet:
        """Get all assignments for a user with channel prefetch."""
        from django.contrib.auth import get_user_model

        user_obj = user
        if isinstance(user, int):
            user_obj = get_user_model().objects.get(id=user)

        return Assignment.objects.for_user(user=user_obj).with_channel()

    @staticmethod
    def get_device_assignments(*, device_id: int) -> QuerySet:
        """Get all assignments for a channel (legacy arg name retained)."""
        return Assignment.objects.filter(channel_id=device_id)

    @staticmethod
    def get_users_with_alerts(*, device_id: int) -> QuerySet:
        """Get users with alerts enabled for a channel (legacy arg name retained)."""
        return (
            Assignment.objects.filter(channel_id=device_id, alert_on_device_offline=True)
            .values_list("user", flat=True)
            .distinct()
        )

    @staticmethod
    def get_assignments_for_user(*, user: User) -> QuerySet[Assignment]:
        """Get all assignments for a user (alias for get_user_assignments)."""
        return AssignmentService.get_user_assignments(user=user)

    @staticmethod
    def get_assignments_for_device(*, device_id: int) -> QuerySet[Assignment]:
        """Get all assignments for a device (alias for get_device_assignments)."""
        return AssignmentService.get_device_assignments(device_id=device_id)

    @staticmethod
    def update_alert_status(*, assignment: Assignment, alert_enabled: bool) -> Assignment:
        """Update the alert status for an assignment."""
        return AssignmentService.update_assignment(
            assignment=assignment, alert_enabled=alert_enabled
        )

    @staticmethod
    def count_total_assignments() -> int:
        """Count total number of assignments."""
        return Assignment.objects.count()

    @staticmethod
    def count_assignments_with_alerts() -> int:
        """Count assignments with device-offline alerts enabled."""
        return Assignment.objects.filter(alert_on_device_offline=True).count()
