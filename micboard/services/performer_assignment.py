"""Performer assignment service layer for binding devices to performers.

Handles assignment lifecycle, state transitions, and lookup helpers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db.models import QuerySet

from micboard.models import PerformerAssignment

if TYPE_CHECKING:
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
                "performer", "wireless_unit", "wireless_unit__base_chassis", "monitoring_group"
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
        user: User | None = None,
    ) -> PerformerAssignment:
        """Create a new performer assignment."""
        assignment = PerformerAssignment.objects.create(
            performer_id=performer_id,
            wireless_unit_id=unit_id,
            monitoring_group_id=group_id,
            priority=priority,
            assigned_by=user,
            is_active=True,
        )

        # Log activity via AuditService (should be called from view or explicitly)
        return assignment

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
