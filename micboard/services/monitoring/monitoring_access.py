"""Monitoring service layer for groups, access control, and alerts.

Handles monitoring group scoping, location/channel access logic,
and alert evaluation entrypoints.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db.models import QuerySet

from micboard.models import Location, MonitoringGroup, RFChannel

if TYPE_CHECKING:  # pragma: no cover
    from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


class MonitoringService:
    """Business logic for monitoring access and alerts."""

    @staticmethod
    def get_user_monitoring_groups(user: User) -> QuerySet[MonitoringGroup]:
        """Get all active monitoring groups for a user."""
        if user.is_superuser:
            return MonitoringGroup.objects.filter(is_active=True)
        return user.monitoring_groups.filter(is_active=True)

    @staticmethod
    def get_accessible_locations(user: User) -> QuerySet[Location]:
        """Get all locations a user has access to via monitoring groups."""
        if user.is_superuser:
            return Location.objects.filter(is_active=True)

        groups = MonitoringService.get_user_monitoring_groups(user)

        # Locations explicitly assigned to groups
        assigned_locations = Location.objects.filter(monitoring_groups__in=groups, is_active=True)

        # Buildings where group has 'include_all_rooms' access
        all_room_buildings = groups.filter(
            monitoringgrouplocation__include_all_rooms=True
        ).values_list("monitoringgrouplocation__location__building", flat=True)

        if all_room_buildings:
            building_locations = Location.objects.filter(
                building_id__in=all_room_buildings, is_active=True
            )
            return (assigned_locations | building_locations).distinct()

        return assigned_locations.distinct()

    @staticmethod
    def get_accessible_channels(user: User) -> QuerySet[RFChannel]:
        """Get all RF channels a user has access to."""
        if user.is_superuser:
            return RFChannel.objects.all()

        groups = MonitoringService.get_user_monitoring_groups(user)

        # 1. Channels explicitly assigned to groups
        explicit_channels = RFChannel.objects.filter(monitoring_groups__in=groups)

        # 2. Channels in accessible locations
        locations = MonitoringService.get_accessible_locations(user)
        location_channels = RFChannel.objects.filter(chassis__location__in=locations)

        return (explicit_channels | location_channels).distinct()

    @staticmethod
    def evaluate_alerts_for_user(user: User) -> list[dict]:
        """Entrypoint for triggering alert evaluation for a specific user.

        Evaluates alert rules against current device telemetry and returns
        a list of triggered alerts for the user's accessible devices.

        Args:
            user: User to evaluate alerts for

        Returns:
            List of alert dictionaries (empty when not implemented)

        Raises:
            NotImplementedError: Alert evaluation rules engine not yet implemented.
        """
        raise NotImplementedError(
            "Alert evaluation rules engine is not yet implemented. "
            "Use MonitoringService from monitoring_service.py for device health metrics instead."
        )
