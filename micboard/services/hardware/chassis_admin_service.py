"""Read services for wireless-chassis admin projections."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Final

from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch, QuerySet

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.rf_coordination.rf_channel import RFChannel
from micboard.services.hardware.chassis_admin_dtos import (
    HardwareLayoutChannel,
    HardwareLayoutChassis,
    HardwareLayoutLocation,
    HardwareLayoutManufacturer,
    HardwareLayoutPage,
    HardwareSummaryChannel,
)
from micboard.services.hardware.dtos import WirelessChassisWrite
from micboard.services.settings.settings_service import settings as micboard_settings
from micboard.services.shared.access_policy import tenant_role_access

CHASSIS_ADMIN_WRITE_FIELDS: Final[tuple[str, ...]] = (
    "role",
    "manufacturer",
    "api_device_id",
    "serial_number",
    "mac_address",
    "model",
    "name",
    "fqdn",
    "description",
    "protocol_family",
    "wmas_capable",
    "licensed_resource_count",
    "ip",
    "subnet_mask",
    "gateway",
    "network_mode",
    "interface_id",
    "mac_address_secondary",
    "ip_address_secondary",
    "firmware_version",
    "hosted_firmware_version",
    "location",
    "order",
    "status",
    "last_seen",
    "is_online",
    "last_online_at",
    "last_offline_at",
    "total_uptime_minutes",
    "max_channels",
    "dante_capable",
    "band_plan_min_mhz",
    "band_plan_max_mhz",
    "band_plan_name",
)


class ChassisAdminDTOMapper:
    """Map eager-loaded chassis and channel models to primitive DTOs."""

    @staticmethod
    def layout_chassis(chassis: WirelessChassis) -> HardwareLayoutChassis:
        """Map one chassis without issuing additional queries."""
        channels = []
        for channel in getattr(chassis, "_admin_layout_channels", []):
            unit = channel.active_wireless_unit or channel.active_iem_receiver
            channels.append(
                HardwareLayoutChannel(
                    channel_number=channel.channel_number,
                    frequency=str(unit.frequency) if unit is not None and unit.frequency else None,
                )
            )
        return HardwareLayoutChassis(
            id=chassis.pk,
            name=chassis.name,
            ip_address=chassis.ip or "Unknown IP",
            channels=channels,
        )

    @staticmethod
    def summary_channel(channel: RFChannel) -> HardwareSummaryChannel:
        """Map one annotated channel without issuing additional queries."""
        unit = channel.active_wireless_unit or channel.active_iem_receiver
        return HardwareSummaryChannel(
            channel_number=channel.channel_number,
            unit_type=unit.device_type.upper() if unit is not None else None,
        )

    @staticmethod
    def write(chassis: WirelessChassis) -> WirelessChassisWrite:
        """Map a complete admin form candidate to the canonical write DTO."""
        return WirelessChassisWrite(
            **{
                field_name: getattr(chassis, field_name)
                for field_name in CHASSIS_ADMIN_WRITE_FIELDS
            }
        )


class ChassisAdminService:
    """Own wireless-chassis admin authorization and read projections."""

    @staticmethod
    def ensure_location_write_allowed(*, user: Any, location: Any | None) -> None:
        """Require tenant operators to keep chassis inside a manageable location."""
        if not (micboard_settings.msp_enabled or micboard_settings.multi_site_mode):
            return
        if location is None:
            if getattr(user, "is_superuser", False):
                return
            raise PermissionDenied("A managed location is required for tenant administrators.")
        if not tenant_role_access.can_manage_object(user=user, obj=location):
            raise PermissionDenied("Select a location you administer.")

    @classmethod
    def get_hardware_layout(
        cls,
        *,
        queryset: QuerySet[WirelessChassis],
    ) -> HardwareLayoutPage:
        """Return active chassis grouped with channels in two bounded queries."""
        channel_queryset = RFChannel.objects.select_related(
            "active_wireless_unit",
            "active_iem_receiver",
        ).order_by("channel_number", "pk")
        chassis_queryset = (
            queryset.filter(status__in=["online", "degraded", "provisioning"])
            .select_related("manufacturer")
            .prefetch_related(
                Prefetch(
                    "rf_channels",
                    queryset=channel_queryset,
                    to_attr="_admin_layout_channels",
                )
            )
            .order_by("manufacturer__name", "ip", "pk")
        )

        grouped: defaultdict[str, defaultdict[str, list[HardwareLayoutChassis]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for chassis in chassis_queryset:
            manufacturer_name = chassis.manufacturer.name if chassis.manufacturer else "Unknown"
            location_name = chassis.ip or "Unknown IP"
            grouped[manufacturer_name][location_name].append(
                ChassisAdminDTOMapper.layout_chassis(chassis)
            )

        return HardwareLayoutPage(
            manufacturers=[
                HardwareLayoutManufacturer(
                    name=manufacturer_name,
                    locations=[
                        HardwareLayoutLocation(name=location_name, chassis=chassis_items)
                        for location_name, chassis_items in locations.items()
                    ],
                )
                for manufacturer_name, locations in grouped.items()
            ]
        )

    @classmethod
    def get_hardware_summary(cls, *, chassis_id: int) -> list[HardwareSummaryChannel]:
        """Return an ordered channel summary in one query, independent of channel count."""
        channels = (
            RFChannel.objects.filter(chassis_id=chassis_id)
            .select_related("active_wireless_unit", "active_iem_receiver")
            .order_by("channel_number", "pk")
        )
        return [ChassisAdminDTOMapper.summary_channel(channel) for channel in channels]
