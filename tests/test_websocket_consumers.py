"""Behavioral coverage for websocket consumer adapters and routing."""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

from django.contrib.auth.models import AnonymousUser
from django.test import override_settings

import pytest

from micboard.services.notification.realtime_routing_service import RealtimeRoutingService
from micboard.websockets.consumers import (
    MAX_WEBSOCKET_COMMAND_BYTES,
    MESSAGE_TOO_LARGE_CLOSE_CODE,
    MicboardConsumer,
)


def _consumer(user=None):
    if user is None:
        user = AnonymousUser()
    consumer = object.__new__(MicboardConsumer)
    consumer.scope = {"user": user}
    consumer.channel_layer = SimpleNamespace(group_add=AsyncMock(), group_discard=AsyncMock())
    consumer.channel_name = "channel"
    consumer.accept = AsyncMock()
    consumer.close = AsyncMock()
    consumer.send = AsyncMock()
    return consumer


def test_consumer_adapters_disconnect_receive_and_forward(monkeypatch) -> None:
    def direct_adapter(function, **_kwargs):
        async def invoke(*args, **kwargs):
            return function(*args, **kwargs)

        return invoke

    monkeypatch.setattr("channels.db.database_sync_to_async", direct_adapter)
    monkeypatch.setattr(MicboardConsumer, "_membership_group_names", Mock(return_value=("one",)))
    monkeypatch.setattr(
        RealtimeRoutingService, "can_receive_global_updates", Mock(return_value=True)
    )
    consumer = _consumer(SimpleNamespace(pk=3, is_authenticated=True))
    consumer._current_groups_for_user = AsyncMock(return_value=("one", "two"))

    assert asyncio.run(consumer._active_groups_for_user(3)) == ("one",)
    assert asyncio.run(consumer._can_receive_global_updates(consumer.scope["user"]))
    consumer.room_group_names = ("one", "two")
    asyncio.run(consumer.disconnect(1000))
    assert consumer.channel_layer.group_discard.await_args_list == [
        call("one", "channel"),
        call("two", "channel"),
    ]

    asyncio.run(consumer.receive(text_data='{"command": "ping"}'))
    assert json.loads(consumer.send.await_args.kwargs["text_data"]) == {"type": "pong"}
    asyncio.run(consumer.receive(text_data='{"command": "other"}'))
    asyncio.run(consumer.receive(text_data="invalid"))
    asyncio.run(consumer.receive(bytes_data=b"ignored"))

    for handler, event, expected_type in (
        (consumer.device_update, {"data": {"id": 1}}, "device_update"),
        (consumer.status_update, {"message": "ready"}, "status"),
        (consumer.progress_update, {"status": "running"}, "progress"),
    ):
        asyncio.run(handler(event))
        assert json.loads(consumer.send.await_args.kwargs["text_data"])["type"] == expected_type

    no_groups = _consumer()
    asyncio.run(no_groups.disconnect(1000))


def test_consumer_rejects_untrusted_frames_without_logging_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    consumer = _consumer(SimpleNamespace(pk=3, is_authenticated=True))
    private_value = "private-command-secret"
    malformed = f'{{"command": "ping", "token": "{private_value}"'

    with caplog.at_level(logging.WARNING, logger="micboard.websockets.consumers"):
        asyncio.run(consumer.receive(text_data=malformed))
        asyncio.run(consumer.receive(text_data=json.dumps([private_value])))
        asyncio.run(consumer.receive(text_data="x" * (MAX_WEBSOCKET_COMMAND_BYTES + 1)))

    assert private_value not in caplog.text
    assert "Rejected malformed WebSocket JSON" in caplog.text
    assert "Rejected non-object WebSocket command" in caplog.text
    assert "Rejected oversized WebSocket command" in caplog.text
    consumer.close.assert_awaited_once_with(code=MESSAGE_TOO_LARGE_CLOSE_CODE)


def test_consumer_rejects_oversized_binary_frames() -> None:
    consumer = _consumer(SimpleNamespace(pk=3, is_authenticated=True))

    asyncio.run(consumer.receive(bytes_data=b"x" * (MAX_WEBSOCKET_COMMAND_BYTES + 1)))

    consumer.close.assert_awaited_once_with(code=MESSAGE_TOO_LARGE_CLOSE_CODE)


@override_settings(MICBOARD_MSP_ENABLED=True)
def test_msp_consumer_without_persisted_user_id_fails_closed() -> None:
    consumer = _consumer(SimpleNamespace(pk=None, is_authenticated=True))
    asyncio.run(consumer.connect())
    consumer.close.assert_awaited_once()
    consumer.accept.assert_not_awaited()


def test_consumer_module_provides_optional_channels_fallback(monkeypatch) -> None:
    """Importing without Channels still provides a harmless consumer base."""
    import micboard.utils.dependencies as dependencies
    import micboard.websockets as websockets_package
    import micboard.websockets.consumers as consumers_module

    module_name = consumers_module.__name__
    original = sys.modules.pop(module_name)
    monkeypatch.setattr(dependencies, "HAS_CHANNELS", False)
    try:
        fallback_module = importlib.import_module(module_name)
        fallback_consumer = fallback_module.AsyncWebsocketConsumer()
        assert fallback_consumer.__class__.__name__ == "AsyncWebsocketConsumer"
    finally:
        sys.modules.pop(module_name, None)
        sys.modules[module_name] = original
        websockets_package.consumers = original


def test_websocket_route_targets_micboard_consumer() -> None:
    """ASGI routing exposes the documented hardware update socket path."""
    from micboard.websockets.routing import websocket_urlpatterns

    assert len(websocket_urlpatterns) == 1
    assert str(websocket_urlpatterns[0].pattern) == "ws"


@pytest.mark.parametrize(
    "relative_path",
    (
        "docs/quickstart.md",
        "docs/installation.md",
        "docs/guides/realtime-updates.md",
    ),
)
def test_channels_documentation_validates_websocket_origins(relative_path: str) -> None:
    """Public ASGI examples must validate origins before authenticating sockets."""
    document = (Path(__file__).resolve().parents[1] / relative_path).read_text()

    assert "from channels.security.websocket import AllowedHostsOriginValidator" in document
    assert (
        '"websocket": AllowedHostsOriginValidator(\n'
        "        AuthMiddlewareStack(URLRouter(websocket_urlpatterns))\n"
        "    ),"
    ) in document
