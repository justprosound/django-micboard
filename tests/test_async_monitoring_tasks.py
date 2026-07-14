"""Regression coverage for ORM work inside hardware event loops."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import pytest

from micboard.integrations.sennheiser.plugin import SennheiserPlugin
from micboard.management.commands.sse_subscribe import Command as SSESubscribeCommand
from micboard.management.commands.websocket_subscribe import Command as WebSocketSubscribeCommand
from micboard.models.discovery import Manufacturer
from micboard.models.hardware import WirelessChassis
from micboard.models.realtime import RealTimeConnection
from micboard.services.notification.broadcast_service import BroadcastService
from micboard.tasks.monitoring.sse import (
    _process_sse_update_async,
    _subscribe_device_async,
)
from micboard.tasks.monitoring.websocket import (
    _process_websocket_update_async,
    _start_receiver_websocket_async,
)
from tests.async_utils import run_async_with_heartbeat
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory


def _manufacturer(**kwargs: Any) -> Manufacturer:
    return cast(Manufacturer, ManufacturerFactory(**kwargs))


def _chassis(**kwargs: Any) -> WirelessChassis:
    return cast(WirelessChassis, WirelessChassisFactory(**kwargs))


def test_sennheiser_plugin_awaits_native_sse_subscription() -> None:
    """The plugin exposes the asynchronous SSE contract used by task and CLI loops."""
    plugin = object.__new__(SennheiserPlugin)
    plugin.client = Mock()
    callback = AsyncMock()
    subscribe = AsyncMock()

    with patch(
        "micboard.integrations.sennheiser.sse_client.connect_and_subscribe",
        subscribe,
    ):
        asyncio.run(plugin.connect_and_subscribe("device-1", callback))

    subscribe.assert_awaited_once_with(plugin.client, "device-1", callback)


class EventPlugin:
    """Small plugin double that leaves database behavior real."""

    def __init__(self, manufacturer: Any, chassis: Any) -> None:
        self.manufacturer = manufacturer
        self.chassis = chassis

    async def connect_and_subscribe(
        self,
        device_id: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Deliver one event through the production async callback."""
        await callback({"id": device_id, "name": "Callback update"})

    def transform_device_data(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Normalize one event into the polling helper's expected shape."""
        return {
            "api_device_id": self.chassis.api_device_id,
            "ip": str(self.chassis.ip),
            "type": self.chassis.model,
            "name": data.get("name", self.chassis.name),
            "firmware": self.chassis.firmware_version,
        }

    def get_device_channels(self, device_id: str) -> list[dict[str, Any]]:
        """Return no channel updates for this chassis-focused regression."""
        return []


class ConnectionOnlyPlugin(EventPlugin):
    """Deliver callbacks without invoking the separate persistence regression."""

    def transform_device_data(self, data: dict[str, Any]) -> None:
        """Skip device updates while connection tracking is under test."""
        return None


class FailingSSEPlugin(ConnectionOnlyPlugin):
    """Raise a private transport detail after connection tracking starts."""

    async def connect_and_subscribe(
        self,
        device_id: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        raise RuntimeError("private credential detail")


@pytest.mark.django_db(transaction=True)
def test_sse_subscription_adapts_connection_tracking_to_sync_database() -> None:
    """SSE callbacks can create and update real connection rows from an event loop."""
    manufacturer = _manufacturer()
    chassis = _chassis(
        manufacturer=manufacturer,
        status="online",
    )
    plugin = ConnectionOnlyPlugin(manufacturer, chassis)

    run_async_with_heartbeat(_subscribe_device_async(plugin, chassis.api_device_id))

    connection = RealTimeConnection.objects.get(chassis=chassis)
    assert connection.connection_type == "sse"
    assert connection.status == "connected"
    assert connection.last_message_at is not None


@pytest.mark.django_db(transaction=True)
def test_sse_connection_error_state_excludes_private_exception_details() -> None:
    """Admin-visible connection state stores only a bounded exception category."""
    manufacturer = _manufacturer()
    chassis = _chassis(manufacturer=manufacturer, status="online")

    run_async_with_heartbeat(
        _subscribe_device_async(
            FailingSSEPlugin(manufacturer, chassis),
            chassis.api_device_id,
        )
    )

    connection = RealTimeConnection.objects.get(chassis=chassis)
    assert connection.status == "error"
    assert connection.error_message == "SSE subscription failed: RuntimeError"
    assert "private credential detail" not in connection.error_message


@pytest.mark.django_db(transaction=True)
def test_websocket_subscription_adapts_connection_tracking_to_sync_database() -> None:
    """Shure callbacks can create and update real connection rows from an event loop."""
    manufacturer = _manufacturer(code="shure")
    chassis = _chassis(
        manufacturer=manufacturer,
        status="online",
    )
    plugin = ConnectionOnlyPlugin(manufacturer, chassis)
    client = Mock()
    client_threads: list[int] = []
    close_threads: list[int] = []

    def make_client(**_kwargs: Any) -> Mock:
        client_threads.append(threading.get_ident())
        return client

    client.close.side_effect = lambda: close_threads.append(threading.get_ident())
    event_loop_thread = threading.get_ident()

    async def deliver_one_event(
        client: Any,
        device_id: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        await callback({"id": device_id, "name": "Callback update"})

    with (
        patch(
            "micboard.tasks.monitoring.websocket.connect_and_subscribe",
            side_effect=deliver_one_event,
        ),
        patch(
            "micboard.integrations.shure.client.ShureSystemAPIClient",
            side_effect=make_client,
        ),
    ):
        run_async_with_heartbeat(_start_receiver_websocket_async(plugin, chassis))

    connection = RealTimeConnection.objects.get(chassis=chassis)
    assert connection.connection_type == "websocket"
    assert connection.status == "connected"
    assert connection.last_message_at is not None
    client.close.assert_called_once_with()
    assert client_threads and client_threads[0] != event_loop_thread
    assert close_threads and close_threads[0] != event_loop_thread


@pytest.mark.django_db(transaction=True)
def test_websocket_connection_error_state_excludes_private_exception_details() -> None:
    """WebSocket failures persist a category without transport or credential text."""
    manufacturer = _manufacturer(code="shure")
    chassis = _chassis(manufacturer=manufacturer, status="online")
    plugin = ConnectionOnlyPlugin(manufacturer, chassis)
    client = Mock()

    async def fail_subscription(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("private credential detail")

    with (
        patch(
            "micboard.tasks.monitoring.websocket.connect_and_subscribe",
            side_effect=fail_subscription,
        ),
        patch(
            "micboard.integrations.shure.client.ShureSystemAPIClient",
            return_value=client,
        ),
    ):
        run_async_with_heartbeat(_start_receiver_websocket_async(plugin, chassis))

    connection = RealTimeConnection.objects.get(chassis=chassis)
    assert connection.status == "error"
    assert connection.error_message == "WebSocket subscription failed: RuntimeError"
    assert "private credential detail" not in connection.error_message
    client.close.assert_called_once_with()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "process_update",
    [_process_sse_update_async, _process_websocket_update_async],
    ids=["sse", "websocket"],
)
def test_realtime_updates_adapt_model_persistence_and_broadcast_lookup(
    process_update: Callable[[Any, str, dict[str, Any]], Awaitable[None]],
) -> None:
    """Both event transports persist and broadcast through sync Django services safely."""
    manufacturer = _manufacturer()
    chassis = _chassis(
        manufacturer=manufacturer,
        name="Before event",
        status="online",
    )
    plugin = EventPlugin(manufacturer, chassis)

    with patch.object(BroadcastService, "broadcast_device_update") as broadcast:
        run_async_with_heartbeat(
            process_update(
                plugin,
                chassis.api_device_id,
                {"id": chassis.api_device_id, "name": "After event"},
            )
        )

    chassis.refresh_from_db()
    assert chassis.name == "After event"
    broadcast.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_sse_management_command_adapts_model_persistence() -> None:
    """The standalone SSE command keeps its callback writes off the event loop."""
    manufacturer = _manufacturer()
    chassis = _chassis(
        manufacturer=manufacturer,
        name="Before command event",
        status="online",
    )
    plugin = EventPlugin(manufacturer, chassis)

    run_async_with_heartbeat(
        SSESubscribeCommand()._process_sse_update(
            plugin,
            chassis.api_device_id,
            {"id": chassis.api_device_id, "name": "After command event"},
        )
    )

    chassis.refresh_from_db()
    assert chassis.name == "After command event"


@pytest.mark.django_db(transaction=True)
def test_websocket_management_command_adapts_model_persistence() -> None:
    """The standalone WebSocket command keeps callback writes off the event loop."""
    manufacturer = _manufacturer(code="shure")
    chassis = _chassis(
        manufacturer=manufacturer,
        name="Before command event",
        status="online",
    )
    plugin = EventPlugin(manufacturer, chassis)

    run_async_with_heartbeat(
        WebSocketSubscribeCommand()._process_websocket_update(
            plugin,
            chassis.api_device_id,
            {"id": chassis.api_device_id, "name": "After command event"},
        )
    )

    chassis.refresh_from_db()
    assert chassis.name == "After command event"


@pytest.mark.django_db(transaction=True)
def test_websocket_management_command_adapts_lookup_and_closes_client() -> None:
    """The standalone WebSocket command resolves ORM state and closes its sync client safely."""
    manufacturer = _manufacturer(code="shure")
    chassis = _chassis(
        manufacturer=manufacturer,
        status="online",
    )
    plugin = ConnectionOnlyPlugin(manufacturer, chassis)
    client = Mock()

    async def deliver_one_event(
        hardware_client: Any,
        device_id: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        await callback({"id": device_id, "name": "Command callback"})

    with (
        patch(
            "micboard.management.commands.websocket_subscribe.connect_and_subscribe",
            side_effect=deliver_one_event,
        ),
        patch(
            "micboard.integrations.shure.client.ShureSystemAPIClient",
            return_value=client,
        ),
    ):
        run_async_with_heartbeat(
            WebSocketSubscribeCommand()._subscribe_device(plugin, chassis.api_device_id)
        )

    client.close.assert_called_once_with()
