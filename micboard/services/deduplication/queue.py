from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction

from micboard.services.deduplication.result import DeduplicationResult

if TYPE_CHECKING:
    from micboard.models.discovery.manufacturer import Manufacturer
    from micboard.models.discovery.queue import DiscoveryQueue

logger = logging.getLogger(__name__)


@transaction.atomic
def queue_for_approval(
    *,
    manufacturer: Manufacturer,
    api_data: dict[str, Any],
    dedup_result: DeduplicationResult,
) -> DiscoveryQueue:
    """Add discovered device to approval queue.

    Args:
        manufacturer: Device manufacturer
        api_data: Raw API device data
        dedup_result: Deduplication check result

    Returns:
        DiscoveryQueue instance
    """
    from micboard.models.discovery.queue import DiscoveryQueue

    serial_number = api_data.get("serial_number") or api_data.get("serialNumber") or ""
    api_device_id = api_data.get("id") or api_data.get("api_device_id") or ""
    ip = api_data.get("ip") or api_data.get("ipAddress") or ""
    device_type = api_data.get("device_type") or api_data.get("model") or "unknown"
    name = api_data.get("name") or ""
    firmware = api_data.get("firmware_version") or api_data.get("firmware") or ""

    if dedup_result.is_conflict:
        status = "pending"
    elif dedup_result.is_duplicate:
        status = "duplicate"
    else:
        status = "pending"

    queue_entry = DiscoveryQueue.objects.create(
        manufacturer=manufacturer,
        serial_number=serial_number,
        api_device_id=api_device_id,
        ip=ip,
        device_type=device_type,
        name=name,
        firmware_version=firmware,
        metadata=api_data,
        status=status,
        existing_device=dedup_result.existing_device,
        is_duplicate=dedup_result.is_duplicate or dedup_result.is_moved,
        is_ip_conflict=dedup_result.is_conflict,
    )

    logger.info(
        "Queued device for approval: %s (%s) - Status: %s",
        name or api_device_id,
        serial_number or ip,
        status,
    )

    return queue_entry


def get_pending_approvals(
    manufacturer: Manufacturer | None = None,
) -> list[DiscoveryQueue]:
    """Get list of devices pending approval."""
    from micboard.models.discovery.queue import DiscoveryQueue

    qs = DiscoveryQueue.objects.filter(status="pending")

    if manufacturer:
        qs = qs.filter(manufacturer=manufacturer)

    return list(qs.select_related("manufacturer", "existing_device"))
