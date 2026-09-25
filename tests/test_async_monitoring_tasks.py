"""Regression coverage for ORM work inside hardware event loops."""

from __future__ import annotations

import threading
from collections.abc import Awaitable, Callable
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import pytest

from micboard.integrations.shure.plugin import ShurePlugin
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.realtime.connection import RealTimeConnection
from micboard.services.common.base.plugin import RealtimeTransport
from micboard.services.core.hardware import NormalizedChassis
from micboard.services.notification.broadcast_service import BroadcastService
from micboard.services.realtime.subscription_lifecycle_service import (
    RealtimeSubscriptionLifecycleService,
)
from micboard.services.realtime.subscription_runner import _subscribe_chassis
from tests.async_utils import run_async_with_heartbeat
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory


def _manufacturer(**kwargs: Any) -> Manufacturer:
    return cast(Manufacturer, ManufacturerFactory(**kwargs))


def _chassis(**kwargs: Any) -> WirelessChassis:
    return cast(WirelessChassis, WirelessChassisFactory(**kwargs))


class EventPlugin:
    """Small plugin double that leaves database behavior real."""

    def __init__(self, manufacturer: Any, chassis: Any, transport: str = "sse") -> None:
        self.manufacturer = manufacturer
        self.chassis = chassis
        self.realtime_transport = transport

    async def subscribe_to_chassis(
        self,
        chassis: Any,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Deliver one event through the production async callback."""
        await callback({"id": chassis.api_device_id, "name": "Callback update"})

    def normalize_device(self, data: dict[str, Any]) -> NormalizedChassis | None:
        """Normalize one event for this chassis."""
        return NormalizedChassis(
            api_device_id=self.chassis.api_device_id,
            ip=str(self.chassis.ip),
            model=self.chassis.model,
            name=data.get("name", self.chassis.name),
            firmware_version=self.chassis.firmware_version,
        )

    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        """Return no channel updates for this chassis-focused regression."""
        return []

    def normalize_channels(self, api_channels: list[dict[str, Any]]) -> list[Any]:
        """Return no channels for this chassis-focused regression."""
        return []


class ConnectionOnlyPlugin(EventPlugin):
    """Deliver callbacks without invoking the separate persistence regression."""

    def normalize_device(self, data: dict[str, Any]) -> None:
        """Skip device updates while connection tracking is under test."""
        return None


class FailingPlugin(ConnectionOnlyPlugin):
    """Raise a private transport detail after connection tracking starts."""

    async def subscribe_to_chassis(
        self,
        chassis: Any,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        raise RuntimeError("private credential detail")


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("transport", ["sse", "websocket"])
def test_subscription_adapts_connection_tracking_to_sync_database(
    transport: RealtimeTransport,
) -> None:
    """Realtime callbacks can create and update real connection rows from an event loop."""
    manufacturer = _manufacturer()
    chassis = _chassis(manufacturer=manufacturer, status="online")
    plugin = ConnectionOnlyPlugin(manufacturer, chassis, transport=transport)

    run_async_with_heartbeat(_subscribe_chassis(plugin, transport, chassis))

    connection = RealTimeConnection.objects.get(chassis=chassis)
    assert connection.connection_type == transport
    # The callback wrote through the thread hop, which is what this covers; the stream then
    # returned, so the round closed the row rather than leaving it claiming to be connected.
    assert connection.last_message_at is not None
    assert connection.status == "stopped"


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("transport", ["sse", "websocket"])
def test_connection_error_state_excludes_private_exception_details(
    transport: RealtimeTransport,
) -> None:
    """Admin-visible connection state stores only a bounded exception category."""
    manufacturer = _manufacturer()
    chassis = _chassis(manufacturer=manufacturer, status="online")

    run_async_with_heartbeat(
        _subscribe_chassis(FailingPlugin(manufacturer, chassis, transport), transport, chassis)
    )

    connection = RealTimeConnection.objects.get(chassis=chassis)
    assert connection.status == "error"
    assert connection.error_message == f"{transport} subscription failed: RuntimeError"
    assert "private credential detail" not in connection.error_message


@pytest.mark.django_db(transaction=True)
def test_shure_opens_and_closes_its_device_client_off_the_event_loop() -> None:
    """Constructing and closing a per-chassis client is synchronous, blocking work."""
    manufacturer = _manufacturer(code="shure")
    chassis = _chassis(manufacturer=manufacturer, status="online")
    plugin = ShurePlugin(manufacturer)
    client = Mock()
    client_threads: list[int] = []
    close_threads: list[int] = []

    def make_client(**_kwargs: Any) -> Mock:
        client_threads.append(threading.get_ident())
        return client

    client.close.side_effect = lambda: close_threads.append(threading.get_ident())
    event_loop_thread = threading.get_ident()

    async def deliver_one_event(
        _client: Any,
        _device_id: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        await callback({"id": "ignored"})

    with (
        patch(
            "micboard.integrations.shure.websocket.connect_and_subscribe",
            side_effect=deliver_one_event,
        ),
        patch(
            "micboard.integrations.shure.plugin.ShureSystemAPIClient",
            side_effect=make_client,
        ),
    ):
        run_async_with_heartbeat(plugin.subscribe_to_chassis(chassis, AsyncMock()))

    client.close.assert_called_once_with()
    assert client_threads and client_threads[0] != event_loop_thread
    assert close_threads and close_threads[0] != event_loop_thread


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("transport", ["sse", "websocket"])
def test_realtime_updates_adapt_model_persistence_and_broadcast_lookup(
    transport: RealtimeTransport,
) -> None:
    """The shared event lifecycle persists and broadcasts outside the event-loop thread."""
    manufacturer = _manufacturer()
    chassis = _chassis(
        manufacturer=manufacturer,
        name="Before event",
        status="online",
    )
    plugin = EventPlugin(manufacturer, chassis, transport=transport)

    with patch.object(BroadcastService, "broadcast_device_update") as broadcast:
        run_async_with_heartbeat(
            RealtimeSubscriptionLifecycleService.process_update(
                plugin=plugin,
                data={"id": chassis.api_device_id, "name": "After event"},
                transport=transport,
            )
        )

    chassis.refresh_from_db()
    assert chassis.name == "After event"
    broadcast.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_a_cancelled_subscription_does_not_leave_the_connection_open() -> None:
    """Supervisor rotation cancels the task, and `CancelledError` is not an `Exception`.

    Without explicit cleanup the row keeps whatever state it reached, so an operator reading
    the admin sees a connection that is still connecting or connected long after it ended.
    """
    import asyncio

    manufacturer = _manufacturer()
    chassis = _chassis(manufacturer=manufacturer, status="online")
    streaming = asyncio.Event()

    class HangingPlugin(ConnectionOnlyPlugin):
        async def subscribe_to_chassis(self, chassis: Any, callback: Any) -> None:
            streaming.set()
            await asyncio.Event().wait()

    async def cancel_mid_subscription() -> None:
        task = asyncio.create_task(
            _subscribe_chassis(HangingPlugin(manufacturer, chassis), "sse", chassis)
        )
        # Wait for the stream to actually open rather than guessing at a delay, so the
        # cancellation lands where this test means it to on any machine.
        await asyncio.wait_for(streaming.wait(), timeout=10)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    run_async_with_heartbeat(cancel_mid_subscription())

    connection = RealTimeConnection.objects.get(chassis=chassis)
    assert connection.status not in {"connecting", "connected"}


@pytest.mark.django_db(transaction=True)
def test_cancellation_during_tracking_setup_still_closes_the_row() -> None:
    """Cancellation can arrive before the round holds the row it already marked connecting."""
    manufacturer = _manufacturer()
    chassis = _chassis(manufacturer=manufacturer, status="online")

    run_async_with_heartbeat(
        _close_tracking_async(chassis),
    )

    connection = RealTimeConnection.objects.get(chassis=chassis)
    assert connection.status == "stopped"


@pytest.mark.django_db(transaction=True)
def test_a_subscription_that_returns_normally_closes_its_connection() -> None:
    """A stream that ends on its own is finished, not still connected."""
    manufacturer = _manufacturer()
    chassis = _chassis(manufacturer=manufacturer, status="online")

    run_async_with_heartbeat(
        _subscribe_chassis(ConnectionOnlyPlugin(manufacturer, chassis), "sse", chassis)
    )

    connection = RealTimeConnection.objects.get(chassis=chassis)
    assert connection.status == "stopped"


@pytest.mark.django_db(transaction=True)
def test_a_failed_subscription_keeps_its_error_state() -> None:
    """Cleanup must not overwrite the error an operator needs to see."""
    manufacturer = _manufacturer()
    chassis = _chassis(manufacturer=manufacturer, status="online")

    run_async_with_heartbeat(
        _subscribe_chassis(FailingPlugin(manufacturer, chassis, "sse"), "sse", chassis)
    )

    connection = RealTimeConnection.objects.get(chassis=chassis)
    assert connection.status == "error"


async def _close_tracking_async(chassis: Any) -> None:
    """Create tracking, then close it the way a cancelled round does, with no handle."""
    from asgiref.sync import sync_to_async

    from micboard.services.realtime.subscription_runner import (
        _close_tracking,
        _track_connection,
    )

    await sync_to_async(_track_connection, thread_sensitive=True)(chassis, "sse")
    await sync_to_async(_close_tracking, thread_sensitive=True)(chassis, None)
