"""Health-related background tasks for the micboard app."""

# Health-related background tasks for the micboard app.
from __future__ import annotations

import logging

from django.core.cache import cache

from micboard.models.discovery import Manufacturer
from micboard.models.telemetry import APIHealthLog
from micboard.services.common.base.plugin import get_manufacturer_plugin
from micboard.services.notification.broadcast_service import BroadcastService
from micboard.services.realtime.health_dtos import RealtimeConnectionHealthResult
from micboard.services.realtime.health_service import RealtimeConnectionHealthService
from micboard.services.shared.api_health import (
    API_HEALTH_AGGREGATE_CACHE_KEY,
    API_HEALTH_SNAPSHOT_CACHE_PREFIX,
    sanitize_public_api_health_snapshot,
)
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


def check_selected_api_server_connections(
    api_server_ids: list[int],
    actor_id: int,
    using: str = "default",
) -> dict[str, int | bool]:
    """Run one bounded API server health-check batch outside the request process."""
    from micboard.services.integrations.api_server_service import APIServerConnectionService

    return APIServerConnectionService.test_selected_connections(
        api_server_ids=api_server_ids,
        actor_id=actor_id,
        using=using,
    ).model_dump()


def _publish_manufacturer_api_health(manufacturer: Manufacturer, health_data: object) -> None:
    """Persist and emit one bounded, secret-safe manufacturer health snapshot."""
    snapshot = sanitize_public_api_health_snapshot(health_data)
    snapshot_data = snapshot.model_dump(exclude_none=True)
    APIHealthLog.objects.create(
        manufacturer=manufacturer,
        status=snapshot.status,
        response_time=snapshot.response_time,
        error_message=snapshot.error or "",
        details=snapshot_data,
    )
    cache.set(
        f"{API_HEALTH_SNAPSHOT_CACHE_PREFIX}{manufacturer.code}",
        snapshot_data,
        timeout=60,
    )
    cache.delete(API_HEALTH_AGGREGATE_CACHE_KEY)
    logger.info("API health for %s: %s", manufacturer.code, snapshot_data)
    BroadcastService.broadcast_api_health(manufacturer=manufacturer, health_data=snapshot_data)


def check_manufacturer_api_health(manufacturer_id: int) -> None:
    """Task to check a specific manufacturer's API health."""
    try:
        manufacturer = Manufacturer.objects.get(pk=manufacturer_id, is_active=True)
    except Manufacturer.DoesNotExist:
        logger.warning(
            "Manufacturer with ID %s not found or inactive for API health check task.",
            manufacturer_id,
        )
        return
    except Exception as exc:
        logger.exception(
            "Error loading manufacturer ID %s for API health check",
            manufacturer_id,
            exc_info=sanitized_exception_info(exc),
        )
        return

    try:
        plugin_class = get_manufacturer_plugin(manufacturer.code)
        plugin = plugin_class(manufacturer)
        health_status: object = plugin.get_client().check_health()
    except Exception as exc:
        logger.exception(
            "Error checking API health for manufacturer ID %s",
            manufacturer_id,
            exc_info=sanitized_exception_info(exc),
        )
        health_status = {"status": "error", "error": True}

    try:
        _publish_manufacturer_api_health(manufacturer, health_status)
    except Exception as exc:
        logger.exception(
            "Error publishing API health for manufacturer ID %s",
            manufacturer_id,
            exc_info=sanitized_exception_info(exc),
        )


def check_realtime_connection_health() -> dict[str, int | bool | str | None]:
    """Run one bounded real-time connection maintenance sweep."""
    try:
        result = RealtimeConnectionHealthService.cleanup()
        logger.info(
            "Real-time connection health check: %d active, %d errors, %d stale reset",
            result.active,
            result.errors,
            result.stale_disconnected,
        )
        return result.model_dump()
    except Exception as exc:
        logger.exception(
            "Error checking real-time connection health",
            exc_info=sanitized_exception_info(exc),
        )
        return RealtimeConnectionHealthResult(
            failed=True,
            error_type=type(exc).__name__,
        ).model_dump()
