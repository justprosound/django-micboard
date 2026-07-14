"""Native Huey task entry points for manufacturer polling."""

# Polling-related background tasks for the micboard app.
from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied

from micboard.models.discovery import Manufacturer
from micboard.models.hardware import WirelessChassis
from micboard.models.integrations import ManufacturerAPIServer

logger = logging.getLogger(__name__)


def poll_api_server_device(
    api_server_id: int,
    chassis_id: int,
) -> dict[str, int] | None:
    """Poll one API-server-owned chassis through the service layer."""
    try:
        server = ManufacturerAPIServer.objects.get(pk=api_server_id)
        chassis = WirelessChassis.objects.select_related("manufacturer", "location").get(
            pk=chassis_id
        )

        from micboard.services.sync.polling_api import APIServerPollingService

        updated = APIServerPollingService.poll_managed_device(
            server=server,
            chassis=chassis,
        )
        return {
            "api_server_id": server.pk,
            "chassis_id": chassis.pk,
            "devices_updated": updated,
        }
    except (ManufacturerAPIServer.DoesNotExist, WirelessChassis.DoesNotExist):
        logger.warning(
            "API server %s or managed chassis %s was not found for polling",
            api_server_id,
            chassis_id,
        )
    except PermissionDenied:
        logger.warning(
            "Rejected API server %s ownership claim for managed chassis %s",
            api_server_id,
            chassis_id,
        )
    except Exception as exc:
        from micboard.utils.exception_logging import sanitized_exception_info

        logger.exception(
            "Failed to poll managed chassis %s through API server %s",
            chassis_id,
            api_server_id,
            exc_info=sanitized_exception_info(exc),
        )
    return None


def refresh_selected_chassis(
    chassis_ids: list[int],
    actor_id: int,
    *,
    using: str = "default",
) -> dict[str, int | bool]:
    """Refresh an authorized, bounded admin selection in a native Huey worker."""
    from micboard.services.hardware.chassis_refresh_service import ChassisRefreshService

    result = ChassisRefreshService.refresh_authorized_ids(
        chassis_ids=chassis_ids,
        actor_id=actor_id,
        using=using,
    )
    return result.model_dump()


def poll_manufacturer_devices(
    manufacturer_id: int,
    *,
    force: bool = False,
) -> dict[str, Any] | None:
    """Poll one currently active manufacturer unless an operator explicitly forced it."""
    try:
        manufacturer_filters: dict[str, int | bool] = {"pk": manufacturer_id}
        if not force:
            manufacturer_filters["is_active"] = True
        manufacturer = Manufacturer.objects.get(**manufacturer_filters)

        # Use the new PollingService for clean service-based approach
        from micboard.services.sync.polling_service import PollingService

        service = PollingService()
        result = service.poll_manufacturer(manufacturer, force=force)

        from micboard.services.monitoring.poll_alert_service import PollAlertService

        alert_scan = PollAlertService.evaluate_manufacturer(manufacturer)

        logger.info(
            "Polling task complete for %s: %d devices created/updated, %d transmitters",
            manufacturer.name,
            result.get("devices_created", 0) + result.get("devices_updated", 0),
            result.get("units_synced", 0),
        )
        if alert_scan.failed:
            logger.warning(
                "Post-poll alert evaluation failed for %d of %d bounded wireless units",
                alert_scan.failed,
                alert_scan.scanned,
            )

        return result

    except Manufacturer.DoesNotExist:
        logger.warning(
            "Manufacturer with ID %s not found or inactive for device polling task.",
            manufacturer_id,
        )
    except Exception as exc:
        from micboard.utils.exception_logging import sanitized_exception_info

        logger.exception(
            "Error polling devices for manufacturer ID %s",
            manufacturer_id,
            exc_info=sanitized_exception_info(exc),
        )
    return None
