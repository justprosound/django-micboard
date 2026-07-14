"""Read services for wireless-chassis admin projections."""

from __future__ import annotations

from collections import defaultdict

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


class ChassisAdminService:
    """Own query planning and grouping for wireless-chassis admin displays."""

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
