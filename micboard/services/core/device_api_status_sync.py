"""Leaf service for optional manufacturer status synchronization."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from micboard.utils.exception_logging import sanitized_exception_info

if TYPE_CHECKING:
    from micboard.models.hardware.wireless_chassis import WirelessChassis
    from micboard.models.hardware.wireless_unit import WirelessUnit

logger = logging.getLogger(__name__)


def sync_status_to_api(
    service_code: str,
    device: WirelessChassis | WirelessUnit,
    status: str,
    metadata: dict[str, Any] | None,
) -> None:
    """Offer a persisted status transition to its manufacturer plugin."""
    try:
        from micboard.services.manufacturer.plugin_registry import PluginRegistry

        plugin = PluginRegistry.get_plugin(service_code)
        if plugin:
            logger.info(
                "Plugin available for %s; status sync may need a vendor implementation",
                service_code,
                extra={
                    "device_id": device.pk,
                    "status": status,
                    "has_metadata": bool(metadata),
                },
            )
    except Exception as exc:
        logger.exception(
            "Failed to sync status to API",
            extra={"device_id": device.pk, "status": status},
            exc_info=sanitized_exception_info(exc),
        )
