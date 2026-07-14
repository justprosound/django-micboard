from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from micboard.models.discovery.manufacturer import Manufacturer
    from micboard.models.discovery.queue import DeviceMovementLog
    from micboard.models.hardware.wireless_chassis import WirelessChassis

logger = logging.getLogger(__name__)


@transaction.atomic
def log_device_movement(
    device: WirelessChassis,
    old_ip: str | None = None,
    new_ip: str | None = None,
    old_location=None,
    new_location=None,
    detected_by: str = "auto",
    reason: str = "",
) -> DeviceMovementLog:
    """Log device movement (IP or location change).

    Args:
        device: Device that moved
        old_ip: Previous IP address
        new_ip: New IP address
        old_location: Previous location
        new_location: New location
        detected_by: How movement was detected
        reason: Movement reason/notes

    Returns:
        DeviceMovementLog instance
    """
    from micboard.models.discovery.queue import DeviceMovementLog

    movement = DeviceMovementLog.objects.create(
        device=device,
        old_ip=old_ip,
        new_ip=new_ip,
        old_location=old_location,
        new_location=new_location,
        detected_by=detected_by,
        reason=reason,
    )

    logger.info(
        "Logged movement for %s: %s",
        device.name or device.api_device_id,
        movement.movement_type,
    )

    return movement


def get_unacknowledged_movements(
    manufacturer: Manufacturer | None = None,
) -> list[DeviceMovementLog]:
    """Get list of unacknowledged device movements."""
    from micboard.models.discovery.queue import DeviceMovementLog

    qs = DeviceMovementLog.objects.filter(acknowledged=False)

    if manufacturer:
        qs = qs.filter(device__manufacturer=manufacturer)

    return list(qs.select_related("device", "old_location", "new_location"))
