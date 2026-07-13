"""Monitoring service layer for groups, access control, and alerts.

Handles monitoring group scoping, location/channel access logic,
and alert evaluation entrypoints.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.db.models import QuerySet

from micboard.models.hardware.charger import Charger, ChargerSlot
from micboard.models.hardware.display_wall import DisplayWall, WallSection
from micboard.models.locations.structure import Building, Location, Room
from micboard.models.monitoring.group import MonitoringGroup
from micboard.models.rf_coordination.rf_channel import RFChannel

logger = logging.getLogger(__name__)


class MonitoringService:
    """Business logic for monitoring access and alerts."""

    @staticmethod
    def _apply_tenant_scope(queryset: QuerySet, *, user: Any) -> QuerySet:
        """Intersect monitoring-group results with active MSP memberships."""
        if not getattr(settings, "MICBOARD_MSP_ENABLED", False):
            return queryset

        from micboard.models.base_managers import TenantOptimizedQuerySet

        tenant_queryset: QuerySet = TenantOptimizedQuerySet(
            queryset.model,
            using=queryset.db,
        ).for_user(user=user)
        return queryset.filter(pk__in=tenant_queryset.values("pk"))

    @staticmethod
    def get_user_monitoring_groups(user: Any) -> QuerySet[MonitoringGroup]:
        """Get all active monitoring groups for a user."""
        if user.is_superuser:
            return MonitoringGroup.objects.filter(is_active=True)
        return user.monitoring_groups.filter(is_active=True)

    @staticmethod
    def get_accessible_locations(user: Any) -> QuerySet[Location]:
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
            visible_locations = (assigned_locations | building_locations).distinct()
        else:
            visible_locations = assigned_locations.distinct()

        return MonitoringService._apply_tenant_scope(visible_locations, user=user)

    @staticmethod
    def get_accessible_buildings(user: Any) -> QuerySet[Building]:
        """Get buildings containing at least one location visible to the user."""
        if user.is_superuser:
            return Building.objects.all()

        locations = MonitoringService.get_accessible_locations(user)
        return Building.objects.filter(locations__in=locations).distinct()

    @staticmethod
    def get_accessible_rooms(user: Any) -> QuerySet[Room]:
        """Get rooms containing at least one location visible to the user."""
        if user.is_superuser:
            return Room.objects.all()

        locations = MonitoringService.get_accessible_locations(user)
        return Room.objects.filter(locations__in=locations).distinct()

    @staticmethod
    def get_accessible_channels(user: Any) -> QuerySet[RFChannel]:
        """Get all RF channels a user has access to."""
        if user.is_superuser:
            return RFChannel.objects.all()

        groups = MonitoringService.get_user_monitoring_groups(user)

        # 1. Channels explicitly assigned to groups
        explicit_channels = RFChannel.objects.filter(monitoring_groups__in=groups)

        # 2. Channels in accessible locations
        locations = MonitoringService.get_accessible_locations(user)
        location_channels = RFChannel.objects.filter(chassis__location__in=locations)

        visible_channels = (explicit_channels | location_channels).distinct()
        return MonitoringService._apply_tenant_scope(visible_channels, user=user)

    @staticmethod
    def get_accessible_chargers(user: Any) -> QuerySet[Charger]:
        """Get chargers installed in locations visible to the user."""
        return Charger.objects.for_user(user=user)

    @staticmethod
    def get_accessible_charger_slots(user: Any) -> QuerySet[ChargerSlot]:
        """Get charger slots whose parent charger is visible to the user."""
        chargers = MonitoringService.get_accessible_chargers(user)
        return ChargerSlot.objects.filter(charger__in=chargers)

    @staticmethod
    def get_accessible_display_walls(user: Any) -> QuerySet[DisplayWall]:
        """Get display walls installed in locations visible to the user."""
        return DisplayWall.objects.for_user(user=user)

    @staticmethod
    def get_accessible_wall_sections(user: Any) -> QuerySet[WallSection]:
        """Get wall sections whose parent display wall is visible to the user."""
        walls = MonitoringService.get_accessible_display_walls(user)
        return WallSection.objects.filter(wall__in=walls)

    @staticmethod
    def evaluate_alerts_for_user(user: Any) -> list[dict]:
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
