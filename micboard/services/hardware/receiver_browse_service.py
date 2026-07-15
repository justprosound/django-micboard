"""Tenant-scoped, paginated chassis browsing."""

from __future__ import annotations

from typing import Any

from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, QuerySet
from django.http import QueryDict

from micboard.filters import HAS_DJANGO_FILTER, WirelessChassisFilter
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.hardware.receiver_browse_dtos import (
    ReceiverBrowseCriteria,
    ReceiverBrowseItem,
    ReceiverBrowsePage,
)


class ReceiverBrowseDTOMapper:
    """Map chassis rows to stable receiver-browse DTOs."""

    @staticmethod
    def from_model(chassis: WirelessChassis) -> ReceiverBrowseItem:
        """Project one prefetched chassis without further database access."""
        location = chassis.location
        return ReceiverBrowseItem(
            id=chassis.pk,
            name=chassis.name or chassis.model or chassis.api_device_id,
            manufacturer_name=chassis.manufacturer.name,
            model_name=chassis.model,
            role=chassis.role,
            role_label=chassis.get_role_display(),
            status=chassis.status,
            status_label=chassis.get_status_display(),
            ip_address=chassis.ip,
            building_name=location.building.name if location else None,
            room_name=location.room.name if location and location.room else None,
        )


class ReceiverBrowseService:
    """Own receiver filtering, eager loading, pagination, and projection."""

    PAGE_SIZE = 24

    @classmethod
    def get_page(
        cls,
        *,
        user: Any,
        criteria: ReceiverBrowseCriteria,
        query_params: QueryDict,
    ) -> ReceiverBrowsePage:
        """Return one bounded page of visible online chassis."""
        queryset: QuerySet[WirelessChassis] = WirelessChassis.objects.for_user(user=user).filter(
            is_online=True
        )
        if criteria.role:
            queryset = queryset.filter(role=criteria.role)
        if criteria.building_id is not None:
            queryset = queryset.filter(location__building_id=criteria.building_id)
        if criteria.room_id is not None:
            queryset = queryset.filter(location__room_id=criteria.room_id)
        if criteria.priority or criteria.performer_id is not None:
            visible_assignments = (
                PerformerAssignment.objects.for_user(user=user)
                .active()
                .filter(wireless_unit__base_chassis_id=OuterRef("pk"))
            )
            if criteria.priority:
                visible_assignments = visible_assignments.filter(priority=criteria.priority)
            if criteria.performer_id is not None:
                visible_assignments = visible_assignments.filter(performer_id=criteria.performer_id)
            queryset = queryset.annotate(
                _has_visible_assignment=Exists(visible_assignments)
            ).filter(_has_visible_assignment=True)

        if HAS_DJANGO_FILTER:
            queryset = WirelessChassisFilter(query_params, queryset=queryset).qs
        if criteria.manufacturer_code:
            queryset = queryset.filter(manufacturer__code=criteria.manufacturer_code)

        queryset = (
            queryset.select_related(
                "manufacturer",
                "location__building",
                "location__room",
            )
            .order_by("order", "manufacturer__name", "name", "pk")
            .distinct()
        )
        page = Paginator(queryset, cls.PAGE_SIZE).get_page(query_params.get("page"))
        preserved_query = query_params.copy()
        preserved_query.pop("page", None)

        return ReceiverBrowsePage(
            title=criteria.title,
            items=[ReceiverBrowseDTOMapper.from_model(chassis) for chassis in page.object_list],
            total_count=page.paginator.count,
            page_number=page.number,
            total_pages=page.paginator.num_pages,
            has_previous=page.has_previous(),
            has_next=page.has_next(),
            previous_page=page.previous_page_number() if page.has_previous() else None,
            next_page=page.next_page_number() if page.has_next() else None,
            query_string=preserved_query.urlencode(),
        )
