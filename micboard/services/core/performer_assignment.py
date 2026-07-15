"""Performer assignment service layer for binding devices to performers.

Handles assignment lifecycle, state transitions, and lookup helpers.
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from typing import Any, cast

from django.apps import apps
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, QuerySet, Value, When, Window
from django.db.models.functions import RowNumber

from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.monitoring.group import MonitoringGroup, MonitoringGroupLocation
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.core.performer_assignment_dtos import (
    CreatePerformerAssignment,
    UpdatePerformerAssignment,
)
from micboard.services.monitoring.monitoring_access import MonitoringService
from micboard.services.settings.settings_service import settings as micboard_settings
from micboard.services.shared.access_policy import has_unrestricted_tenant_access

logger = logging.getLogger(__name__)


class PerformerAssignmentService:
    """Business logic for performer-to-device assignments."""

    MODIFY_ROLES = frozenset({"operator", "admin", "owner"})
    PAGE_SIZE = 50

    @staticmethod
    def get_visible_assignments(*, user: Any) -> QuerySet[PerformerAssignment]:
        """Return user-scoped assignments with all row relations eager loaded."""
        return PerformerAssignment.objects.for_user(user=user).select_related(
            "performer",
            "wireless_unit",
            "monitoring_group",
        )

    @staticmethod
    def _normalize_page_number(page: int | str | None) -> int:
        """Return a positive page number without evaluating a paginator."""
        try:
            page_number = int(page or 1)
        except (TypeError, ValueError):
            return 1
        return max(page_number, 1)

    @classmethod
    def get_visible_assignment_rows(
        cls,
        *,
        user: Any,
        page: int | str | None = 1,
    ) -> QuerySet[PerformerAssignment]:
        """Return one bounded live-refresh slice without a count query."""
        page_number = cls._normalize_page_number(page)
        start = (page_number - 1) * cls.PAGE_SIZE
        stop = start + cls.PAGE_SIZE
        return cls.get_visible_assignments(user=user)[start:stop]

    @staticmethod
    def _get_preferred_active_assignments(
        *,
        user: Any,
        filters: dict[str, Any],
    ) -> QuerySet[PerformerAssignment]:
        """Rank candidates in SQL so only one preferred row per unit is materialized."""
        priority = Case(
            When(priority="critical", then=Value(0)),
            When(priority="high", then=Value(1)),
            When(priority="normal", then=Value(2)),
            When(priority="low", then=Value(3)),
            default=Value(4),
            output_field=IntegerField(),
        )
        return cast(
            QuerySet[PerformerAssignment],
            (
                PerformerAssignment.objects.for_user(user=user)
                .filter(is_active=True, **filters)
                .annotate(
                    _preferred_rank=Window(
                        expression=RowNumber(),
                        partition_by=[F("wireless_unit_id")],
                        order_by=[
                            priority.asc(),
                            F("updated_at").desc(),
                            F("pk").desc(),
                        ],
                    )
                )
                .filter(_preferred_rank=1)
                .select_related("performer", "wireless_unit")
                .order_by("wireless_unit_id")
            ),
        )

    @classmethod
    def get_preferred_active_assignments_for_units(
        cls,
        *,
        user: Any,
        unit_ids: Collection[int],
    ) -> QuerySet[PerformerAssignment]:
        """Return at most one deterministic active assignment for each requested unit."""
        if not unit_ids:
            return PerformerAssignment.objects.none()
        return cls._get_preferred_active_assignments(
            user=user,
            filters={"wireless_unit_id__in": unit_ids},
        )

    @classmethod
    def get_preferred_active_assignments_for_serials(
        cls,
        *,
        user: Any,
        serial_numbers: Collection[str],
    ) -> QuerySet[PerformerAssignment]:
        """Return at most one deterministic active assignment for each requested serial."""
        if not serial_numbers:
            return PerformerAssignment.objects.none()
        return cls._get_preferred_active_assignments(
            user=user,
            filters={"wireless_unit__serial_number__in": serial_numbers},
        )

    @staticmethod
    def ensure_group_can_manage_unit(*, group: MonitoringGroup, unit: WirelessUnit) -> None:
        """Require the selected group to cover the unit in tenant-aware deployments."""
        if not (micboard_settings.msp_enabled or micboard_settings.multi_site_mode):
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
        if not micboard_settings.msp_enabled:
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
    def _ensure_mutation_scope(
        *,
        user: Any,
        group: MonitoringGroup,
        unit: WirelessUnit,
    ) -> None:
        """Enforce every tenant relationship required to mutate an assignment."""
        PerformerAssignmentService.ensure_can_modify_unit(user=user, unit=unit)
        PerformerAssignmentService.ensure_group_can_manage_unit(group=group, unit=unit)

    @staticmethod
    def _get_assignment_for_mutation(
        *,
        assignment_id: int,
        user: Any,
    ) -> PerformerAssignment:
        """Lock and return one user-visible assignment with its authorization graph."""
        return (
            PerformerAssignment.objects.for_user(user=user)
            .select_related(
                "monitoring_group",
                "wireless_unit__base_chassis__location__building",
            )
            .select_for_update()
            .get(id=assignment_id)
        )

    @staticmethod
    def create_assignment(
        *,
        command: CreatePerformerAssignment,
        user: Any,
    ) -> PerformerAssignment:
        """Create an assignment after validating every object against user scope."""
        with transaction.atomic():
            try:
                monitoring_group = MonitoringService.get_user_monitoring_groups(user).get(
                    pk=command.group_id,
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

            PerformerAssignmentService._ensure_mutation_scope(
                user=user,
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
        with transaction.atomic():
            assignment = PerformerAssignmentService._get_assignment_for_mutation(
                assignment_id=command.assignment_id,
                user=user,
            )
            PerformerAssignmentService._ensure_mutation_scope(
                user=user,
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
            with transaction.atomic():
                assignment = PerformerAssignmentService._get_assignment_for_mutation(
                    assignment_id=assignment_id,
                    user=user,
                )
                PerformerAssignmentService._ensure_mutation_scope(
                    user=user,
                    group=assignment.monitoring_group,
                    unit=assignment.wireless_unit,
                )
                assignment.delete()
        except PerformerAssignment.DoesNotExist:
            return False
        return True

    @staticmethod
    def deactivate_assignment(*, assignment_id: int, user: Any) -> bool:
        """Deactivate an existing assignment."""
        try:
            with transaction.atomic():
                assignment = PerformerAssignmentService._get_assignment_for_mutation(
                    assignment_id=assignment_id,
                    user=user,
                )
                PerformerAssignmentService._ensure_mutation_scope(
                    user=user,
                    group=assignment.monitoring_group,
                    unit=assignment.wireless_unit,
                )
                assignment.is_active = False
                assignment.save(update_fields=["is_active", "updated_at"])
        except PerformerAssignment.DoesNotExist:
            return False
        return True
