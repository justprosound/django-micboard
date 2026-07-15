from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction

if TYPE_CHECKING:
    from micboard.models.discovery.queue import DeviceMovementLog
    from micboard.models.hardware.wireless_chassis import WirelessChassis
    from micboard.models.locations.structure import Location

logger = logging.getLogger(__name__)


@transaction.atomic
def log_device_movement(
    device: WirelessChassis,
    old_ip: str | None = None,
    new_ip: str | None = None,
    old_location: Location | None = None,
    new_location: Location | None = None,
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
        "Logged device movement (device_id=%s, movement_type=%s)",
        device.pk,
        movement.movement_type,
    )

    return movement
