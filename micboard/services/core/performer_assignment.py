"""Performer assignment service layer for binding devices to performers.

Handles assignment lifecycle, state transitions, and lookup helpers.
"""

from __future__ import annotations

import logging
from typing import Any

from django.apps import apps
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet

from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.monitoring.group import MonitoringGroup
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.shared.access_policy import has_unrestricted_tenant_access

logger = logging.getLogger(__name__)


class PerformerAssignmentService:
    """Business logic for performer-to-device assignments."""

    MODIFY_ROLES = frozenset({"operator", "admin", "owner"})

    @staticmethod
    def ensure_can_modify_unit(*, user: Any, unit: WirelessUnit) -> None:
        """Require an MSP role that permits assignment changes for the unit."""
        if not getattr(settings, "MICBOARD_MSP_ENABLED", False):
            return
        if has_unrestricted_tenant_access(user):
            return
        if not apps.is_installed("micboard.multitenancy"):
            raise PermissionDenied("Multi-tenant assignment access is unavailable")

        location = unit.base_chassis.location
        if location is None:
            raise PermissionDenied("The wireless unit is not assigned to an organization")
        organization_id = location.building.organization_id
        if organization_id is None:
            raise PermissionDenied("The wireless unit is not assigned to an organization")

        from micboard.multitenancy.models import OrganizationMembership

        building = location.building
        campus_scope = (
            Q(campus_id__isnull=True)
            if building.campus_id is None
            else Q(campus_id__isnull=True) | Q(campus_id=building.campus_id)
        )
        can_modify = OrganizationMembership._default_manager.filter(
            user=user,
            organization_id=organization_id,
            organization__is_active=True,
            is_active=True,
            role__in=PerformerAssignmentService.MODIFY_ROLES,
        ).filter(campus_scope)
        if not can_modify.exists():
            raise PermissionDenied("This membership cannot modify device assignments")

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
        user: Any,
        priority: str = "normal",
        notes: str | None = None,
        alert_on_battery_low: bool | None = None,
        alert_on_signal_loss: bool | None = None,
        alert_on_audio_low: bool | None = None,
        alert_on_hardware_offline: bool | None = None,
        is_active: bool = True,
    ) -> PerformerAssignment:
        """Create an assignment after validating every object against user scope."""
        from django.db import transaction

        with transaction.atomic():
            try:
                monitoring_group = (
                    MonitoringGroup.objects.get(pk=group_id, is_active=True)
                    if has_unrestricted_tenant_access(user)
                    else user.monitoring_groups.get(pk=group_id, is_active=True)
                )
                performer = Performer.objects.for_user(user=user).get(pk=performer_id)
                wireless_unit = WirelessUnit.objects.for_user(user=user).get(pk=unit_id)
            except (
                MonitoringGroup.DoesNotExist,
                Performer.DoesNotExist,
                WirelessUnit.DoesNotExist,
            ):
                raise PermissionDenied(
                    "Assignment references an object outside the user's scope"
                ) from None

            PerformerAssignmentService.ensure_can_modify_unit(user=user, unit=wireless_unit)

            assignment = PerformerAssignment.objects.create(
                performer=performer,
                wireless_unit=wireless_unit,
                monitoring_group=monitoring_group,
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
        user: Any,
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
            assignment = (
                PerformerAssignment.objects.for_user(user=user)
                .select_related("wireless_unit__base_chassis__location__building")
                .select_for_update()
                .get(id=assignment_id)
            )
            PerformerAssignmentService.ensure_can_modify_unit(
                user=user,
                unit=assignment.wireless_unit,
            )

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
    def delete_assignment(*, assignment_id: int, user: Any) -> bool:
        """Permanently delete an assignment. Returns True if deleted, False if not found."""
        try:
            assignment = (
                PerformerAssignment.objects.for_user(user=user)
                .select_related("wireless_unit__base_chassis__location__building")
                .get(id=assignment_id)
            )
            PerformerAssignmentService.ensure_can_modify_unit(
                user=user,
                unit=assignment.wireless_unit,
            )
            assignment.delete()
            return True
        except PerformerAssignment.DoesNotExist:
            return False

    @staticmethod
    def deactivate_assignment(*, assignment_id: int, user: Any) -> bool:
        """Deactivate an existing assignment."""
        try:
            assignment = (
                PerformerAssignment.objects.for_user(user=user)
                .select_related("wireless_unit__base_chassis__location__building")
                .get(id=assignment_id)
            )
            PerformerAssignmentService.ensure_can_modify_unit(
                user=user,
                unit=assignment.wireless_unit,
            )
            assignment.is_active = False
            assignment.save(update_fields=["is_active", "updated_at"])
            return True
        except PerformerAssignment.DoesNotExist:
            return False
