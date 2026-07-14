"""Behavioral coverage for the Shure WebSocket transport."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import micboard.integrations.shure.websocket as websocket_module
from micboard.integrations.shure.exceptions import ShureAPIError
from tests.vendor_test_helpers import (
    DirectAsyncAdapter,
    VendorConnection,
    disable_rate_limit_waits,
)


@pytest.fixture(autouse=True)
def _disable_rate_limit_waits(monkeypatch) -> None:
    disable_rate_limit_waits(monkeypatch)


def test_websocket_helpers_parse_subscribe_and_dispatch() -> None:
    assert websocket_module._parse_transport_id_from_message(b'{"transportId": "transport"}') == (
        "transport"
    )
    assert websocket_module._parse_transport_id_from_message(b"\xff") is None
    assert websocket_module._parse_transport_id_from_message("not-json") is None

    client = SimpleNamespace(_make_request=Mock(return_value={"status": "success"}))
    websocket_module._subscribe_client_to_transport(client, "device", "transport")
    client._make_request.assert_called_once_with(
        "POST", "/api/v1/devices/device/identify/subscription/transport"
    )
    client._make_request.return_value = {"status": "failed"}
    with pytest.raises(websocket_module.ShureWebSocketError):
        websocket_module._subscribe_client_to_transport(client, "device", "transport")
    client._make_request.side_effect = ShureAPIError("subscription failed")
    with pytest.raises(ShureAPIError):
        websocket_module._subscribe_client_to_transport(client, "device", "transport")

    callback = Mock(side_effect=[None, RuntimeError("handler failed")])
    async_callback = AsyncMock()

    class Socket:
        def __aiter__(self):
            self.messages = iter(['{"one": 1}', '{"two": 2}', "bad-json", '{"three": 3}'])
            return self

        async def __anext__(self):
            try:
                return next(self.messages)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    asyncio.run(websocket_module._read_and_dispatch_messages(Socket(), "device", callback))
    assert callback.call_count == 3

    class AsyncSocket(Socket):
        def __aiter__(self):
            self.messages = iter(['{"async": true}'])
            return self

    asyncio.run(
        websocket_module._read_and_dispatch_messages(AsyncSocket(), "device", async_callback)
    )
    async_callback.assert_awaited_once_with({"async": True})


def test_websocket_connect_rejects_missing_dependency_url_and_handshake(monkeypatch) -> None:
    callback = AsyncMock()
    client = SimpleNamespace(websocket_url="wss://shure.test", _make_request=Mock())
    monkeypatch.setattr(websocket_module, "HAS_WEBSOCKETS", False)
    with pytest.raises(websocket_module.ShureWebSocketError, match="dependency missing"):
        asyncio.run(websocket_module.connect_and_subscribe(client, "device", callback))

    monkeypatch.setattr(websocket_module, "HAS_WEBSOCKETS", True)
    monkeypatch.setattr(websocket_module, "websockets", SimpleNamespace(connect=Mock()))
    client.websocket_url = None
    with pytest.raises(websocket_module.ShureWebSocketError, match="not configured"):
        asyncio.run(websocket_module.connect_and_subscribe(client, "device", callback))

    class Socket:
        async def recv(self):
            return "{}"

    class Connection:
        async def __aenter__(self):
            return Socket()

        async def __aexit__(self, *_args):
            return None

    client.websocket_url = "wss://shure.test"
    websocket_module.websockets.connect.return_value = Connection()
    with pytest.raises(websocket_module.ShureWebSocketError, match="transportId"):
        asyncio.run(websocket_module.connect_and_subscribe(client, "device", callback))


def test_websocket_connect_dispatches_and_classifies_connection_failures(monkeypatch) -> None:
    connect = Mock(return_value=VendorConnection())
    monkeypatch.setattr(websocket_module, "HAS_WEBSOCKETS", True)
    monkeypatch.setattr(websocket_module, "websockets", SimpleNamespace(connect=connect))
    monkeypatch.setattr(websocket_module, "sync_to_async", DirectAsyncAdapter())
    callback = AsyncMock()
    client = SimpleNamespace(
        websocket_url="wss://shure.test/events",
        _make_request=Mock(return_value={"status": "success"}),
    )

    asyncio.run(websocket_module.connect_and_subscribe(client, "device", callback))
    callback.assert_awaited_once_with({"status": "online"})

    graceful_error = type("GracefulClose", (Exception,), {})
    connection_error = type("ConnectionFailure", (Exception,), {})
    monkeypatch.setattr(websocket_module, "WebsocketClosedOKError", graceful_error)
    monkeypatch.setattr(websocket_module, "WebsocketConnectionClosedError", connection_error)

    connect.return_value = VendorConnection(error=graceful_error())
    asyncio.run(websocket_module.connect_and_subscribe(client, "device", callback))

    connect.return_value = VendorConnection(error=connection_error())
    with pytest.raises(websocket_module.ShureWebSocketError, match="connection error"):
        asyncio.run(websocket_module.connect_and_subscribe(client, "device", callback))

    connect.return_value = VendorConnection(error=RuntimeError("unexpected"))
    with pytest.raises(websocket_module.ShureWebSocketError, match="Unhandled"):
        asyncio.run(websocket_module.connect_and_subscribe(client, "device", callback))

    client._make_request.side_effect = ShureAPIError("REST failed")
    connect.return_value = VendorConnection()
    with pytest.raises(ShureAPIError, match="REST failed"):
        asyncio.run(websocket_module.connect_and_subscribe(client, "device", callback))
