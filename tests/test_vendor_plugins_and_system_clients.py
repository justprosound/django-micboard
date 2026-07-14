"""Behavioral coverage for vendor plugin and system-client boundaries."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

import micboard.integrations.sennheiser.sse_client as sse_module
import micboard.integrations.shure.websocket as websocket_module
from micboard.integrations.sennheiser.client import SennheiserSystemAPIClient
from micboard.integrations.sennheiser.exceptions import SennheiserAPIError
from micboard.integrations.sennheiser.plugin import SennheiserPlugin
from micboard.integrations.shure.client import ShureSystemAPIClient
from micboard.integrations.shure.exceptions import ShureAPIError
from micboard.integrations.shure.plugin import ShurePlugin
from micboard.services.settings.settings_service import settings as app_settings
from tests.vendor_test_helpers import disable_rate_limit_waits


@pytest.fixture(autouse=True)
def _disable_rate_limit_waits(monkeypatch) -> None:
    disable_rate_limit_waits(monkeypatch)


def test_shure_plugin_delegates_to_lazy_client_and_transformer(monkeypatch) -> None:
    client = SimpleNamespace(
        devices=SimpleNamespace(
            get_devices=Mock(return_value=[{"id": "one"}]),
            get_device=Mock(return_value={"id": "one"}),
            get_device_channels=Mock(return_value=[]),
        ),
        discovery=SimpleNamespace(
            add_discovery_ips=Mock(return_value=True),
            get_discovery_ips=Mock(return_value=["192.0.2.1"]),
            remove_discovery_ips=Mock(return_value=True),
        ),
        connect_and_subscribe=AsyncMock(),
        is_healthy=Mock(return_value=True),
        check_health=Mock(return_value={"status": "healthy"}),
    )
    factory = Mock(return_value=client)
    monkeypatch.setattr("micboard.integrations.shure.plugin.ShureSystemAPIClient", factory)
    plugin = ShurePlugin(SimpleNamespace(code="shure"))
    plugin.transformer = SimpleNamespace(
        transform_device_data=Mock(return_value={"id": "normalized"}),
        transform_transmitter_data=Mock(return_value={"slot": 1}),
    )

    assert plugin.name == "Shure"
    assert plugin.code == "shure"
    assert plugin.get_client() is client
    assert plugin.get_client() is client
    factory.assert_called_once_with()
    assert plugin.get_devices() == [{"id": "one"}]
    assert plugin.get_device("one") == {"id": "one"}
    assert plugin.get_device_channels("one") == []
    assert plugin.transform_device_data({}) == {"id": "normalized"}
    assert plugin.transform_transmitter_data({}, 1) == {"slot": 1}
    assert plugin.is_healthy()
    assert plugin.check_health() == {"status": "healthy"}
    assert plugin.add_discovery_ips(["192.0.2.1"])
    assert plugin.get_discovery_ips() == ["192.0.2.1"]
    assert plugin.remove_discovery_ips(["192.0.2.1"])

    subscribe = AsyncMock()
    monkeypatch.setattr(websocket_module, "connect_and_subscribe", subscribe)
    asyncio.run(plugin.connect_and_subscribe("one", AsyncMock()))
    subscribe.assert_awaited_once()


def test_sennheiser_plugin_delegates_to_client_transformer_and_sse(monkeypatch) -> None:
    client = SimpleNamespace(
        devices=SimpleNamespace(
            get_devices=Mock(return_value=[]),
            get_device=Mock(return_value=None),
            get_device_channels=Mock(return_value=[]),
        ),
        discovery=SimpleNamespace(
            add_discovery_ips=Mock(return_value=True),
            get_discovery_ips=Mock(return_value=[]),
            remove_discovery_ips=Mock(return_value=True),
        ),
        connect_and_subscribe=AsyncMock(),
        is_healthy=Mock(return_value=True),
        check_health=Mock(return_value={"status": "healthy"}),
    )
    monkeypatch.setattr(
        "micboard.integrations.sennheiser.plugin.SennheiserSystemAPIClient",
        Mock(return_value=client),
    )
    plugin = SennheiserPlugin(SimpleNamespace(code="sennheiser"))
    plugin.transformer = SimpleNamespace(
        transform_device_data=Mock(return_value={"id": "normalized"}),
        transform_transmitter_data=Mock(return_value={"slot": 2}),
    )
    assert plugin.name == "Sennheiser"
    assert plugin.code == "sennheiser"
    assert plugin.get_client() is client
    assert plugin.get_devices() == []
    assert plugin.get_device("one") is None
    assert plugin.get_device_channels("one") == []
    assert plugin.transform_device_data({}) == {"id": "normalized"}
    assert plugin.transform_transmitter_data({}, 2) == {"slot": 2}
    assert plugin.is_healthy()
    assert plugin.check_health() == {"status": "healthy"}
    assert plugin.add_discovery_ips([])
    assert plugin.get_discovery_ips() == []
    assert plugin.remove_discovery_ips([])
    asyncio.run(plugin.connect_and_subscribe("one", AsyncMock()))
    client.connect_and_subscribe.assert_awaited_once()


def test_system_clients_validate_auth_and_websocket_configuration(monkeypatch) -> None:
    monkeypatch.setattr(app_settings, "get_config_dict", lambda: {})
    with pytest.raises(ValueError, match="SENNHEISER_API_PASSWORD"):
        SennheiserSystemAPIClient()
    with pytest.raises(ValueError, match="SHURE_API_SHARED_KEY"):
        ShureSystemAPIClient()

    monkeypatch.setattr(
        app_settings,
        "get_config_dict",
        lambda: {"SHURE_API_SHARED_KEY": "secret", "SHURE_API_USE_DIGEST": True},
    )
    monkeypatch.setattr(httpx, "DigestAuth", Mock(side_effect=RuntimeError("unsupported")))
    with ShureSystemAPIClient(base_url="https://shure.test") as client:
        assert client._get_config_prefix() == "SHURE_API"
        assert client._get_default_base_url().startswith("https://")
        assert client._get_health_check_endpoint() == "/api/v1/devices"
        assert client.get_exception_class() is ShureAPIError
        assert client.websocket_url == "wss://shure.test/api/v1/subscriptions/websocket/create"
        client.websocket_url = "wss://events.test/path"
        assert client.websocket_url == "wss://events.test/path"
        client.websocket_url = None
        assert client.websocket_url is None
        with pytest.raises(ValueError, match="absolute WSS URL"):
            client.websocket_url = "ws://cleartext.test"
        with pytest.raises(ValueError, match="absolute WSS URL"):
            client._validate_websocket_url("not a url")
        with pytest.raises(ValueError, match="absolute WSS URL"):
            client._validate_websocket_url(None)  # type: ignore[arg-type]
        client.base_url = ""
        client._explicit_websocket_set = False
        assert client.websocket_url is None

    monkeypatch.setattr(
        app_settings,
        "get_config_dict",
        lambda: {"SENNHEISER_API_PASSWORD": "secret"},
    )
    with SennheiserSystemAPIClient() as client:
        assert client._get_config_prefix() == "SENNHEISER_API"
        assert client._get_default_base_url().startswith("https://")
        assert client._get_health_check_endpoint() == "/api/ssc/version"
        assert client.get_exception_class() is SennheiserAPIError
        assert client.get_rate_limit_exception_class().__name__ == "SennheiserAPIRateLimitError"
        subscribe = AsyncMock()
        monkeypatch.setattr(sse_module, "connect_and_subscribe", subscribe)
        callback = AsyncMock()
        asyncio.run(client.connect_and_subscribe("one", callback))
        subscribe.assert_awaited_once_with(client, "one", callback)

    monkeypatch.setattr(
        app_settings,
        "get_config_dict",
        lambda: {
            "SHURE_API_SHARED_KEY": "secret",
            "SHURE_API_WEBSOCKET_URL": "wss://events.test/stream",
        },
    )
    with ShureSystemAPIClient(base_url="https://shure.test") as client:
        assert client.websocket_url == "wss://events.test/stream"


def test_sse_client_handles_non_success_and_wraps_transport_error(monkeypatch) -> None:
    class StreamResponse:
        status_code = 503
        headers: dict[str, str] = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    class StreamClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def stream(self, *_args, **_kwargs):
            return StreamResponse()

    monkeypatch.setattr(sse_module.httpx, "AsyncClient", lambda **_kwargs: StreamClient())
    client = SimpleNamespace(
        base_url="https://sennheiser.test",
        username="api",
        password="secret",
    )
    with pytest.raises(SennheiserAPIError, match="status 503"):
        asyncio.run(sse_module.connect_and_subscribe(client, "one", AsyncMock()))

    monkeypatch.setattr(
        sse_module.httpx,
        "AsyncClient",
        Mock(side_effect=RuntimeError("transport down")),
    )
    with pytest.raises(SennheiserAPIError, match="subscription failed"):
        asyncio.run(sse_module.connect_and_subscribe(client, "one", AsyncMock()))


@pytest.mark.parametrize(
    "content_location",
    [
        None,
        "https://attacker.example/api/ssc/state/subscriptions/session",
        "/api/ssc/state/not-subscriptions/session",
        "/api/ssc/state/subscriptions/",
    ],
)
def test_sse_subscription_control_url_rejects_unsafe_locations(content_location) -> None:
    with pytest.raises(SennheiserAPIError):
        sse_module._subscription_control_url(
            base_url="https://sennheiser.test",
            content_location=content_location,
        )
