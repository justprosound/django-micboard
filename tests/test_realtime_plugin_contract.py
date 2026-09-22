"""What an integration must say about its realtime stream.

The shared runner drives whichever transport an integration speaks, so the integration
declares the transport and owns the connection. Nothing outside the integration package
knows how a vendor's stream is opened.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from micboard.integrations.sennheiser.plugin import SennheiserPlugin
from micboard.integrations.shure.plugin import ShurePlugin
from micboard.services.common.base.plugin import ManufacturerPlugin


def test_every_shipped_integration_declares_its_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The runner reads the transport off the plugin rather than inferring it from a code."""
    monkeypatch.setattr(
        "micboard.integrations.sennheiser.plugin.SennheiserSystemAPIClient",
        Mock(),
    )

    assert ShurePlugin(None).realtime_transport == "websocket"
    assert SennheiserPlugin(None).realtime_transport == "sse"


def test_the_plugin_contract_requires_a_transport_declaration() -> None:
    """A plugin cannot ship without saying whether and how it streams."""
    assert "realtime_transport" in ManufacturerPlugin.__abstractmethods__
    assert "subscribe_to_chassis" in ManufacturerPlugin.__abstractmethods__


def test_shure_streams_a_chassis_over_its_own_device_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shure receivers are subscribed directly, so the client targets the chassis address."""
    client = Mock()
    factory = Mock(return_value=client)
    monkeypatch.setattr("micboard.integrations.shure.plugin.ShureSystemAPIClient", factory)
    subscribe = AsyncMock()
    monkeypatch.setattr("micboard.integrations.shure.websocket.connect_and_subscribe", subscribe)
    plugin = ShurePlugin(SimpleNamespace(code="shure", pk=1))
    chassis = SimpleNamespace(ip="192.0.2.40", port=8443, api_device_id="device-1", pk=7)
    callback = AsyncMock()

    asyncio.run(plugin.subscribe_to_chassis(chassis, callback))

    factory.assert_called_once_with(base_url="https://192.0.2.40:8443")
    subscribe.assert_awaited_once_with(client, "device-1", callback)
    client.close.assert_called_once_with()


def test_shure_closes_its_device_connection_after_a_stream_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed subscription cannot leak the per-chassis transport it opened."""
    client = Mock()
    monkeypatch.setattr(
        "micboard.integrations.shure.plugin.ShureSystemAPIClient",
        Mock(return_value=client),
    )
    monkeypatch.setattr(
        "micboard.integrations.shure.websocket.connect_and_subscribe",
        AsyncMock(side_effect=RuntimeError("handshake rejected")),
    )
    plugin = ShurePlugin(SimpleNamespace(code="shure", pk=1))
    chassis = SimpleNamespace(ip="192.0.2.40", port=443, api_device_id="device-1", pk=7)

    with pytest.raises(RuntimeError):
        asyncio.run(plugin.subscribe_to_chassis(chassis, AsyncMock()))

    client.close.assert_called_once_with()


def test_sennheiser_streams_a_chassis_through_its_system_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sennheiser subscribes through the manufacturer-level SSCv2 client it already holds."""
    client = Mock()
    client.connect_and_subscribe = AsyncMock()
    monkeypatch.setattr(
        "micboard.integrations.sennheiser.plugin.SennheiserSystemAPIClient",
        Mock(return_value=client),
    )
    plugin = SennheiserPlugin(SimpleNamespace(code="sennheiser", pk=2))
    chassis = SimpleNamespace(api_device_id="device-9", pk=9)
    callback = AsyncMock()

    asyncio.run(plugin.subscribe_to_chassis(chassis, callback))

    client.connect_and_subscribe.assert_awaited_once_with("device-9", callback)
