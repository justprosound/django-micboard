"""Hardware sync operations for status, battery, and channel management.

Provides write operations that synchronize hardware state from external sources.
"""

from __future__ import annotations

import logging

from django.db import DEFAULT_DB_ALIAS

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit

logger = logging.getLogger(__name__)


class HardwareSyncService:
    @staticmethod
    def sync_hardware_status(*, obj: WirelessChassis | WirelessUnit, online: bool) -> None:
        """Update hardware online status.

        Uses direct status update - lifecycle hooks handle timestamps, audit, broadcast.
        """
        obj.status = "online" if online else "offline"
        obj.save(update_fields=["status"])

    @staticmethod
    def ensure_channel_count(
        *,
        chassis: WirelessChassis,
        using: str = DEFAULT_DB_ALIAS,
    ) -> tuple[int, int]:
        """Ensure RFChannel rows for a chassis match its model capacity.

        Returns (created_count, deleted_count).
        """
        from micboard.models.rf_coordination.rf_channel import RFChannel

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
