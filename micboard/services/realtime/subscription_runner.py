"""One bounded realtime subscription run, for whichever transport an integration speaks."""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from typing import Any

from asgiref.sync import sync_to_async

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.common.base.plugin import RealtimeTransport, build_manufacturer_plugin
from micboard.services.manufacturer.activation_service import ManufacturerActivationService
from micboard.services.realtime.subscription_lifecycle_service import (
    RealtimeSubscriptionLifecycleService,
)
from micboard.services.realtime.subscription_supervisor import (
    RealtimeSubscriptionSupervisor,
)
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)


def run_realtime_subscriptions(manufacturer_id: int, *, chassis_id: int | None = None) -> None:
    """Run the singleton, bounded realtime supervisor for one manufacturer.

    The transport is read from the manufacturer's integration rather than chosen by the
    caller: an integration streams over exactly one of them, or over none at all.
    """
    try:
        try:
            manufacturer = Manufacturer.objects.get(pk=manufacturer_id, is_active=True)
        except Manufacturer.DoesNotExist:
            logger.error(
                "Manufacturer with ID %s not found or inactive for realtime subscriptions",
                manufacturer_id,
            )
            return

        plugin = build_manufacturer_plugin(manufacturer)
        transport: RealtimeTransport | None = plugin.realtime_transport
        if transport is None:
            logger.error(
                "The integration for manufacturer ID %s does not stream realtime updates",
                manufacturer_id,
            )
            return

        # Check for work before taking the lease. A lease expires rather than being released,
        # so acquiring one for an empty inventory blocks the next run for its whole timeout.
        if not RealtimeSubscriptionLifecycleService.has_eligible_chassis(
            manufacturer_id=manufacturer_id,
            chassis_id=chassis_id,
        ):
            logger.info(
                "No active chassis found for %s subscriptions on manufacturer ID %s",
                transport,
                manufacturer_id,
            )
            return

        limits = RealtimeSubscriptionSupervisor.limits()
        lease = RealtimeSubscriptionSupervisor.acquire(transport=transport, scope=manufacturer_id)
        if lease is None:
            logger.info(
                "A %s subscription supervisor is already active for manufacturer ID %s",
                transport,
                manufacturer_id,
            )
            return

        def select() -> list[WirelessChassis]:
            return RealtimeSubscriptionLifecycleService.select_chassis(
                manufacturer_id=manufacturer_id,
                chassis_id=chassis_id,
                transport=transport,
                limit=limits.max_devices,
            )

        selected = select()
        if not selected:
            logger.info(
                "No active chassis found for %s subscriptions on manufacturer ID %s",
                transport,
                manufacturer_id,
            )
            return

        async def reload_selection() -> list[WirelessChassis]:
            manufacturer_active = await sync_to_async(
                ManufacturerActivationService.is_active,
                thread_sensitive=True,
            )(manufacturer_id)
            if not manufacturer_active:
                return []
            return await sync_to_async(select, thread_sensitive=True)()

        logger.info(
            "Starting %s subscriptions for %d chassis on manufacturer ID %s",
            transport,
            len(selected),
            manufacturer_id,
        )

        asyncio.run(
            RealtimeSubscriptionSupervisor.run(
                items=selected,
                subscribe=partial(_subscribe_chassis, plugin, transport),
                lease=lease,
                limits=limits,
                reload_items=reload_selection,
            )
        )

    except Exception as exc:
        logger.exception(
            "Error in realtime subscriptions for manufacturer ID %s",
            manufacturer_id,
            exc_info=sanitized_exception_info(exc),
        )


def _close_tracking(chassis: WirelessChassis, connection: Any) -> None:
    """Mark this chassis's connection stopped, even if the caller never captured the row.

    Cancellation can arrive while `_track_connection` is still running, after it has marked
    the row connecting but before the coroutine holds it, so the row is resolved by chassis
    when the local handle is missing.
    """
    from micboard.models.realtime.connection import RealTimeConnection

    tracked = (
        connection
        if connection is not None
        else (RealTimeConnection.objects.filter(chassis=chassis))
    )
    tracked.mark_stopped()


def _track_connection(chassis: WirelessChassis, transport: RealtimeTransport) -> Any:
    """Open connection tracking for one chassis in Django's synchronous context.

    Returns the single-row queryset the round uses to record its outcome, so every
    transition goes through the one definition the admin also uses.
    """
    from micboard.models.realtime.connection import RealTimeConnection

    connection, created = RealTimeConnection.objects.get_or_create(
        chassis=chassis,
        defaults={"connection_type": transport},
    )
    if not created and connection.connection_type != transport:
        connection.connection_type = transport
        connection.save(update_fields=["connection_type", "updated_at"])
    tracked = RealTimeConnection.objects.filter(pk=connection.pk)
    tracked.mark_connecting()
    return tracked


async def _subscribe_chassis(
    plugin: Any,
    transport: RealtimeTransport,
    chassis: WirelessChassis,
) -> None:
    """Stream one chassis through its integration, tracking the connection's outcome."""
    manufacturer_id = plugin.manufacturer.pk
    logger.info(
        "Starting %s subscription for chassis ID %s on manufacturer ID %s",
        transport,
        chassis.pk,
        manufacturer_id,
    )

    connection: Any = None

    async def update_callback(data: dict[str, Any]) -> None:
        if connection is not None:
            await sync_to_async(connection.record_message, thread_sensitive=True)()
        await RealtimeSubscriptionLifecycleService.process_update(
            plugin=plugin,
            data=data,
            transport=transport,
        )

    closed = False
    try:
        connection = await sync_to_async(_track_connection, thread_sensitive=True)(
            chassis,
            transport,
        )
        manufacturer_active = await sync_to_async(
            ManufacturerActivationService.is_active,
            thread_sensitive=True,
        )(manufacturer_id)
        if not manufacturer_active:
            logger.info(
                "%s subscription stopped for inactive manufacturer ID %s",
                transport,
                manufacturer_id,
            )
            await sync_to_async(connection.mark_stopped, thread_sensitive=True)()
            closed = True
            return
        await plugin.subscribe_to_chassis(chassis, update_callback)
    except asyncio.CancelledError:
        # Supervisor rotation and shutdown cancel this task, and `CancelledError` is a
        # `BaseException`, so the handler below never sees it. Close the row here or it keeps
        # claiming to be connecting or connected for as long as it survives.
        logger.info(
            "%s subscription cancelled for chassis ID %s",
            transport,
            chassis.pk,
        )
        await sync_to_async(_close_tracking, thread_sensitive=True)(chassis, connection)
        closed = True
        raise
    except Exception as exc:
        logger.exception(
            "Error in %s subscription for chassis ID %s",
            transport,
            chassis.pk,
            exc_info=sanitized_exception_info(exc),
        )
        if connection is not None:
            error_status = f"{transport} subscription failed: {type(exc).__name__}"[:160]
            await sync_to_async(connection.mark_error, thread_sensitive=True)(error_status)
            closed = True
    finally:
        # A stream that returned on its own is finished, not still connected. A row already
        # marked stopped or errored keeps that state.
        if not closed:
            await sync_to_async(_close_tracking, thread_sensitive=True)(chassis, connection)
