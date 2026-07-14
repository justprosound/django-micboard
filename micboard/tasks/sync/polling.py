"""Native Huey task entry points for manufacturer polling."""

# Polling-related background tasks for the micboard app.
from __future__ import annotations

import logging
from typing import Any

from micboard.models.discovery import Manufacturer
from micboard.models.hardware import WirelessUnit
from micboard.services.monitoring.alerts import (
    check_hardware_offline_alerts,
    check_transmitter_alerts,
)

logger = logging.getLogger(__name__)


def refresh_selected_chassis(
    chassis_ids: list[int],
    *,
    using: str = "default",
) -> dict[str, int]:
    """Refresh an explicit admin selection in a native Huey worker."""
    from micboard.services.hardware.chassis_refresh_service import ChassisRefreshService

    result = ChassisRefreshService.refresh_ids(chassis_ids=chassis_ids, using=using)
    return result.model_dump()


def poll_manufacturer_devices(manufacturer_id: int) -> dict[str, Any] | None:
    """Poll one manufacturer through the service layer and run follow-up work."""
    try:
        manufacturer = Manufacturer.objects.get(pk=manufacturer_id)

        # Use the new PollingService for clean service-based approach
        from micboard.services.sync.polling_service import PollingService

        service = PollingService()
        result = service.poll_manufacturer(manufacturer)

        # Run alerts for each unit after polling.
        for unit in WirelessUnit.objects.filter(manufacturer=manufacturer):
            check_hardware_offline_alerts(unit)
            check_transmitter_alerts(unit)

        logger.info(
            "Polling task complete for %s: %d devices created/updated, %d transmitters",
            manufacturer.name,
            result.get("devices_created", 0) + result.get("devices_updated", 0),
            result.get("units_synced", 0),
        )

        # Start real-time subscriptions
        _start_realtime_subscriptions(manufacturer)

        return result

    except Manufacturer.DoesNotExist:
        logger.warning(
            "Manufacturer with ID %s not found for device polling task.", manufacturer_id
        )
    except Exception as e:
        logger.exception("Error polling devices for manufacturer ID %s: %s", manufacturer_id, e)
    return None


def _start_realtime_subscriptions(manufacturer):
    """Start real-time subscriptions for a manufacturer."""
    from micboard.utils.dependencies import enqueue_huey_task, huey_is_configured

    if not huey_is_configured():
        logger.debug(
            "Native Huey is unavailable or unconfigured; "
            "skipping real-time subscription background tasks"
        )
        return

    try:
        if manufacturer.code == "shure":
            # Start WebSocket subscriptions for Shure
            from micboard.tasks.monitoring.websocket import start_shure_websocket_subscriptions

            enqueue_huey_task(start_shure_websocket_subscriptions)
            logger.info("Started WebSocket subscriptions for %s", manufacturer.name)
        elif manufacturer.code == "sennheiser":
            # Start SSE subscriptions for Sennheiser
            from micboard.tasks.monitoring.sse import start_sse_subscriptions

            enqueue_huey_task(start_sse_subscriptions, manufacturer.id)
            logger.info("Started SSE subscriptions for %s", manufacturer.name)
        else:
            logger.debug("No real-time subscriptions available for %s", manufacturer.code)

    except Exception as e:
        logger.exception("Error starting real-time subscriptions for %s: %s", manufacturer.name, e)
