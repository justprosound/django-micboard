"""Hardware sync operations for status, battery, and channel management.

Provides write operations that synchronize hardware state from external sources.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import DEFAULT_DB_ALIAS

from micboard.models.device_specs import (
    get_channel_count,
    get_dante_support,
    get_device_role,
)
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit

if TYPE_CHECKING:  # pragma: no cover
    pass

logger = logging.getLogger(__name__)


class HardwareSyncService:
    @staticmethod
    def sync_hardware_status(*, obj: WirelessChassis | WirelessUnit, online: bool) -> None:
        """Update hardware online status.

        Uses direct status update - lifecycle hooks handle timestamps, audit, broadcast.
        """
        if isinstance(obj, (WirelessChassis, WirelessUnit)):
            obj.status = "online" if online else "offline"
            obj.save(update_fields=["status"])

    @staticmethod
    def sync_unit_battery(*, unit: WirelessUnit, battery_level: int) -> None:
        """Update field unit battery level."""
        if not (0 <= battery_level <= 255):
            raise ValueError("battery_level must be 0-255")

        if unit.battery != battery_level:
            unit.battery = battery_level
            unit.save(update_fields=["battery", "updated_at"])

    @staticmethod
    def ensure_channel_count(
        *,
        chassis: WirelessChassis,
        using: str = DEFAULT_DB_ALIAS,
    ) -> tuple[int, int]:
        """Ensure RFChannel rows for a chassis match its model capacity.

        Returns (created_count, deleted_count).
        """
        from micboard.models.rf_coordination import RFChannel

        expected = chassis.get_expected_channel_count()
        channels = RFChannel.objects.using(using)
        current_channels = set(
            channels.filter(chassis_id=chassis.pk).values_list("channel_number", flat=True)
        )
        expected_channels = set(range(1, expected + 1))

        created_count = 0
        deleted_count = 0

        for ch_num in sorted(expected_channels - current_channels):
            if chassis.role == "receiver":
                link_direction = "receive"
            elif chassis.role == "transmitter":
                link_direction = "send"
            else:
                link_direction = "bidirectional"

            channels.create(
                chassis_id=chassis.pk,
                channel_number=ch_num,
                link_direction=link_direction,
            )
            created_count += 1

        for ch_num in sorted(current_channels - expected_channels):
            channels.filter(chassis_id=chassis.pk, channel_number=ch_num).delete()
            deleted_count += 1

        return (created_count, deleted_count)

    @staticmethod
    def update_device_capabilities(*, chassis: WirelessChassis) -> None:
        """Update capabilities (max_channels, dante_capable, role) from device specs registry."""
        if not chassis.manufacturer or not chassis.model:
            return

        mfg_code = (
            chassis.manufacturer.code.lower()
            if hasattr(chassis.manufacturer, "code")
            else "unknown"
        )

        old_channels = chassis.max_channels
        old_dante = chassis.dante_capable
        old_role = chassis.role

        chassis.max_channels = get_channel_count(
            manufacturer=mfg_code,
            model=chassis.model,
        )
        chassis.dante_capable = get_dante_support(
            manufacturer=mfg_code,
            model=chassis.model,
        )
        chassis.role = get_device_role(
            manufacturer=mfg_code,
            model=chassis.model,
        )

        if (
            old_channels != chassis.max_channels
            or old_dante != chassis.dante_capable
            or old_role != chassis.role
        ):
            chassis.save(update_fields=["max_channels", "dante_capable", "role"])

    # Async variants

    @staticmethod
    async def async_sync_hardware_status(
        *, obj: WirelessChassis | WirelessUnit, online: bool
    ) -> None:
        """Async: Sync device online status."""
        from asgiref.sync import sync_to_async

        await sync_to_async(HardwareSyncService.sync_hardware_status)(obj=obj, online=online)
