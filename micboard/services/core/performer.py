"""Performer service layer for managing performer records.

Handles performer CRUD operations, search, and list helpers.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import QuerySet

from micboard.models.monitoring.performer import Performer

logger = logging.getLogger(__name__)


class PerformerService:
    """Business logic for performers."""

    @staticmethod
    def get_active_performers() -> QuerySet[Performer]:
        """Get all active performers.

        Returns:
            QuerySet of active performers ordered by name
        """
        return Performer.objects.filter(is_active=True).order_by("name")

    @staticmethod
    def search_performers(*, query: str) -> QuerySet[Performer]:
        """Search performers by name, title, or contact info.

        Args:
            query: Search query string

        Returns:
            QuerySet matching performers
        """
        from django.db.models import Q

        return Performer.objects.filter(
            Q(name__icontains=query)
            | Q(title__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        ).distinct()

    @staticmethod
    def create_performer(
        *,
        name: str,
        title: str = "",
        email: str = "",
        phone: str = "",
        role_description: str = "",
        notes: str = "",
    ) -> Performer:
        """Create a new performer.

        Args:
            name: Performer name (required)
            title: Role or title
            email: Contact email
            phone: Contact phone
            role_description: Description of role and requirements
            notes: Additional notes

        Returns:
            Created Performer instance
        """
        performer = Performer.objects.create(
            name=name,
            title=title,
            email=email,
            phone=phone,
            role_description=role_description,
            notes=notes,
            is_active=True,
        )
        logger.info(f"Created performer: {performer.name}")
        return performer

    @staticmethod
    def update_performer(
        performer: Performer,
        *,
        name: str | None = None,
        title: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        role_description: str | None = None,
        notes: str | None = None,
        is_active: bool | None = None,
    ) -> Performer:
        """Update performer information.

        Args:
            performer: Performer instance to update
            name: New name (if provided)
            title: New title (if provided)
            email: New email (if provided)
            phone: New phone (if provided)
            role_description: New role description (if provided)
            notes: New notes (if provided)
            is_active: New active status (if provided)

        Returns:
            Updated Performer instance
        """
        if name is not None:
            performer.name = name
        if title is not None:
            performer.title = title
        if email is not None:
            performer.email = email
        if phone is not None:
            performer.phone = phone
        if role_description is not None:
            performer.role_description = role_description
        if notes is not None:
            performer.notes = notes
        if is_active is not None:
            performer.is_active = is_active

        performer.save()
        logger.info(f"Updated performer: {performer.name}")
        return performer

    @staticmethod
    def deactivate_performer(performer: Performer) -> None:
        """Deactivate a performer (soft delete).

        Args:
            performer: Performer to deactivate
        """
        performer.is_active = False
        performer.save(update_fields=["is_active"])
        logger.info(f"Deactivated performer: {performer.name}")

    @staticmethod
    def get_performer_assignments(performer: Performer) -> QuerySet:
        """Get all assignments for a performer.

        Args:
            performer: Performer instance

        Returns:
            QuerySet of PerformerAssignment objects
        """
        from micboard.models.monitoring.performer_assignment import PerformerAssignment

        return PerformerAssignment.objects.filter(performer=performer).select_related(
            "wireless_unit", "monitoring_group"
        )

    @staticmethod
    def get_monitoring_groups_for_performer(performer: Performer) -> QuerySet:
        """Get all monitoring groups that manage a performer.

        Args:
            performer: Performer instance

        Returns:
            QuerySet of MonitoringGroup objects
        """
        from micboard.models.monitoring.group import MonitoringGroup

        return MonitoringGroup.objects.filter(performer_assignments__performer=performer).distinct()

    @staticmethod
    def get_performer_details(performer: Performer) -> dict[str, Any]:
        """Get comprehensive detail about a performer including assignments.

        Args:
            performer: Performer instance

        Returns:
            Dictionary with performer info and relations
        """
        assignments = PerformerService.get_performer_assignments(performer)
        groups = PerformerService.get_monitoring_groups_for_performer(performer)

        return {
            "performer": performer,
            "assignments": assignments,
            "assignment_count": assignments.count(),
            "monitoring_groups": groups,
            "group_count": groups.count(),
            "is_active": performer.is_active,
            "last_updated": performer.updated_at,
        }
