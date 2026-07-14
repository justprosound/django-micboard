"""Performer assignment service layer for binding devices to performers.

Handles assignment lifecycle, state transitions, and lookup helpers.
"""

from __future__ import annotations

import logging
from typing import Any

from django.apps import apps
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.monitoring.group import MonitoringGroup, MonitoringGroupLocation
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.core.performer_assignment_dtos import (
    CreatePerformerAssignment,
    UpdatePerformerAssignment,
)
from micboard.services.shared.access_policy import has_unrestricted_tenant_access

logger = logging.getLogger(__name__)


class PerformerAssignmentService:
    """Business logic for performer-to-device assignments."""

    MODIFY_ROLES = frozenset({"operator", "admin", "owner"})

    @staticmethod
    def ensure_group_can_manage_unit(*, group: MonitoringGroup, unit: WirelessUnit) -> None:
        """Require the selected group to cover the unit in tenant-aware deployments."""
        if not (
            getattr(settings, "MICBOARD_MSP_ENABLED", False)
            or getattr(settings, "MICBOARD_MULTI_SITE_MODE", False)
        ):
            return

        location = unit.base_chassis.location
        if location is None:
            raise PermissionDenied("The wireless unit is not assigned to a managed location")

        location_access = MonitoringGroupLocation.objects.filter(
            monitoring_group=group,
        ).filter(
            Q(location_id=location.pk)
            | Q(
                include_all_rooms=True,
                location__building_id=location.building_id,
            )
        )
        channel_access = (
            unit.assigned_resource_id is not None
            and group.channels.filter(pk=unit.assigned_resource_id).exists()
        )
        if not location_access.exists() and not channel_access:
            raise PermissionDenied(
                "The monitoring group does not manage the wireless unit's tenant scope"
            )

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
    def create_assignment(
        *,
        command: CreatePerformerAssignment,
        user: Any,
    ) -> PerformerAssignment:
        """Create an assignment after validating every object against user scope."""
        from django.db import transaction

        with transaction.atomic():
            try:
                monitoring_group = (
                    MonitoringGroup.objects.get(pk=command.group_id, is_active=True)
                    if has_unrestricted_tenant_access(user)
                    else user.monitoring_groups.get(pk=command.group_id, is_active=True)
                )
                performer = Performer.objects.for_user(user=user).get(pk=command.performer_id)
                wireless_unit = (
                    WirelessUnit.objects.for_user(user=user)
                    .select_related("base_chassis__location__building")
                    .get(pk=command.unit_id)
                )
            except (
                MonitoringGroup.DoesNotExist,
                Performer.DoesNotExist,
                WirelessUnit.DoesNotExist,
            ):
                raise PermissionDenied(
                    "Assignment references an object outside the user's scope"
                ) from None

            PerformerAssignmentService.ensure_can_modify_unit(user=user, unit=wireless_unit)
            PerformerAssignmentService.ensure_group_can_manage_unit(
                group=monitoring_group,
                unit=wireless_unit,
            )

            assignment = PerformerAssignment(
                performer=performer,
                wireless_unit=wireless_unit,
                monitoring_group=monitoring_group,
                priority=command.priority,
                notes=command.notes,
                is_active=command.is_active,
                assigned_by=user,
            )
            alert_values = {
                "alert_on_battery_low": command.alert_on_battery_low,
                "alert_on_signal_loss": command.alert_on_signal_loss,
                "alert_on_audio_low": command.alert_on_audio_low,
                "alert_on_hardware_offline": command.alert_on_hardware_offline,
            }
            for field_name, value in alert_values.items():
                if value is not None:
                    setattr(assignment, field_name, value)

            assignment.full_clean()
            assignment.save()

            # TODO: emit audit log / signals if required by calling code
            return assignment

    @staticmethod
    def update_assignment(
        *,
        command: UpdatePerformerAssignment,
        user: Any,
    ) -> PerformerAssignment:
        """Update fields on an existing assignment and return the instance.

        Raises PerformerAssignment.DoesNotExist if the assignment is missing.
        """
        from django.db import transaction

        with transaction.atomic():
            assignment = (
                PerformerAssignment.objects.for_user(user=user)
                .select_related(
                    "monitoring_group",
                    "wireless_unit__base_chassis__location__building",
                )
                .select_for_update()
                .get(id=command.assignment_id)
            )
            PerformerAssignmentService.ensure_can_modify_unit(
                user=user,
                unit=assignment.wireless_unit,
            )
            PerformerAssignmentService.ensure_group_can_manage_unit(
                group=assignment.monitoring_group,
                unit=assignment.wireless_unit,
            )

            update_values = command.model_dump(exclude={"assignment_id"}, exclude_none=True)
            for field_name, value in update_values.items():
                setattr(assignment, field_name, value)

            assignment.full_clean()
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
