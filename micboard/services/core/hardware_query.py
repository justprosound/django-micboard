"""Hardware query operations for chassis and wireless units.

Provides read-only query operations against WirelessChassis and WirelessUnit models.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import models
from django.db.models import QuerySet

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.services.shared.tenant_filters import apply_tenant_filters

if TYPE_CHECKING:  # pragma: no cover
    pass

logger = logging.getLogger(__name__)


class HardwareQueryService:
    @staticmethod
    def get_active_chassis(
        *,
        organization_id: int | None = None,
        site_id: int | None = None,
        campus_id: int | None = None,
    ) -> QuerySet[WirelessChassis]:
        """Fetch all active chassis."""
        qs: QuerySet[WirelessChassis] = WirelessChassis.objects.active()
        return apply_tenant_filters(
            qs,
            organization_id=organization_id,
            campus_id=campus_id,
            site_id=site_id,
            building_path="location__building",
        )

    @staticmethod
    def get_active_units(
        *,
        organization_id: int | None = None,
        site_id: int | None = None,
        campus_id: int | None = None,
    ) -> QuerySet[WirelessUnit]:
        """Fetch all active field units."""
        qs: QuerySet[WirelessUnit] = WirelessUnit.objects.active()
        return apply_tenant_filters(
            qs,
            organization_id=organization_id,
            campus_id=campus_id,
            site_id=site_id,
            building_path="base_chassis__location__building",
        )

    @staticmethod
    def get_chassis_by_ip(*, ip: str) -> WirelessChassis | None:
        """Find a chassis by IP address."""
        return WirelessChassis.objects.filter(ip=ip).first()

    @staticmethod
    def get_chassis_by_id(*, chassis_id: int) -> WirelessChassis:
        """Get a chassis by its ID."""
        from micboard.exceptions import HardwareNotFoundError

        try:
            return WirelessChassis.objects.get(id=chassis_id)
        except WirelessChassis.DoesNotExist:
            raise HardwareNotFoundError(f"Chassis with ID {chassis_id} not found") from None

    @staticmethod
    def get_unit_by_id(*, unit_id: int) -> WirelessUnit:
        """Get a wireless unit by its ID."""
        from micboard.exceptions import HardwareNotFoundError

        try:
            return WirelessUnit.objects.get(id=unit_id)
        except WirelessUnit.DoesNotExist:
            raise HardwareNotFoundError(f"Wireless unit with ID {unit_id} not found") from None

    @staticmethod
    def count_online_hardware() -> dict[str, int]:
        """Get count of online hardware by type."""
        return {
            "chassis": WirelessChassis.objects.filter(is_online=True).count(),
            "units": WirelessUnit.objects.filter(status="online").count(),
        }

    @staticmethod
    def search_hardware(*, query: str) -> list[WirelessChassis | WirelessUnit]:
        """Search hardware by name, IP, or serial number."""
        results: list[WirelessChassis | WirelessUnit] = []

        chassis = WirelessChassis.objects.filter(
            models.Q(name__icontains=query)
            | models.Q(ip__icontains=query)
            | models.Q(serial_number__icontains=query)
        )
        results.extend(list(chassis))

        units = WirelessUnit.objects.filter(
            models.Q(name__icontains=query)
            | models.Q(frequency__icontains=query)
            | models.Q(serial_number__icontains=query)
        )
        results.extend(list(units))

        return results

    # Async variants (Django 4.2+ async view support)

    @staticmethod
    async def aget_active_chassis(
        *,
        organization_id: int | None = None,
        site_id: int | None = None,
    ) -> QuerySet[WirelessChassis]:
        """Async: Get all active chassis."""
        from asgiref.sync import sync_to_async

        return await sync_to_async(HardwareQueryService.get_active_chassis)(
            organization_id=organization_id,
            site_id=site_id,
        )

    @staticmethod
    async def aget_online_chassis(
        *,
        organization_id: int | None = None,
        site_id: int | None = None,
    ) -> QuerySet[WirelessChassis]:
        """Async: Get all online chassis."""
        from asgiref.sync import sync_to_async

        return await sync_to_async(
            lambda: HardwareQueryService.get_active_chassis(
                organization_id=organization_id,
                site_id=site_id,
            ).filter(is_online=True)
        )()

    @staticmethod
    async def aget_chassis_by_id(*, chassis_id: int) -> WirelessChassis:
        """Async: Get chassis by ID."""
        from asgiref.sync import sync_to_async

        return await sync_to_async(HardwareQueryService.get_chassis_by_id)(chassis_id=chassis_id)

    @staticmethod
    async def aget_active_units(
        *,
        organization_id: int | None = None,
        site_id: int | None = None,
    ) -> QuerySet[WirelessUnit]:
        """Async: Get all active wireless units."""
        from asgiref.sync import sync_to_async

        return await sync_to_async(HardwareQueryService.get_active_units)(
            organization_id=organization_id,
            site_id=site_id,
        )

    @staticmethod
    async def aget_unit_by_id(*, unit_id: int) -> WirelessUnit:
        """Async: Get wireless unit by ID."""
        from asgiref.sync import sync_to_async

        return await sync_to_async(HardwareQueryService.get_unit_by_id)(unit_id=unit_id)

    @staticmethod
    async def aget_low_battery_units(*, threshold: int = 20) -> QuerySet[WirelessUnit]:
        """Async: Get wireless units with low battery."""
        from asgiref.sync import sync_to_async

        return await sync_to_async(lambda: WirelessUnit.objects.low_battery(threshold=threshold))()
