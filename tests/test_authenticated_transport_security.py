"""Security regressions for authenticated manufacturer transports."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import httpx
import pytest

import micboard.integrations.shure.websocket as shure_websocket_module
import micboard.services.maintenance.efis_import as efis_import_module
from micboard.integrations.sennheiser.client import SennheiserSystemAPIClient
from micboard.integrations.shure.client import ShureSystemAPIClient
from micboard.services.common.base import client as base_client_module
from micboard.services.common.base import resilience
from micboard.services.settings.settings_service import settings as app_settings


def test_shure_client_uses_httpx_certificate_verification_defaults(monkeypatch) -> None:
    """Shure clients cannot override the httpx TLS verification default."""
    monkeypatch.setattr(
        app_settings,
        "get_config_dict",
        lambda: {"SHURE_API_SHARED_KEY": "test-secret"},
    )
    transport = MagicMock()
    client_factory = MagicMock(return_value=transport)
    monkeypatch.setattr(base_client_module.httpx, "Client", client_factory)

    client = ShureSystemAPIClient(base_url="https://shure.test")

    client_factory.assert_called_once_with(timeout=10)
    assert "verify" not in client_factory.call_args.kwargs
    client.close()


def test_shure_client_explicit_shared_key_overrides_global_configuration(monkeypatch) -> None:
    """Persisted server checks cannot leak a process-global credential."""
    monkeypatch.setattr(
        app_settings,
        "get_config_dict",
        lambda: {"SHURE_API_SHARED_KEY": "global-secret"},
    )

    with ShureSystemAPIClient(
        base_url="https://shure.test",
        shared_key="row-secret",
    ) as client:
        assert client.client.headers["x-api-key"] == "row-secret"


def test_shure_client_rejects_cleartext_base_url(monkeypatch) -> None:
    """API keys cannot be configured on cleartext Shure connections."""
    monkeypatch.setattr(
        app_settings,
        "get_config_dict",
        lambda: {"SHURE_API_SHARED_KEY": "test-secret"},
    )

    with pytest.raises(ValueError, match="SHURE_API_BASE_URL must be an absolute HTTPS URL"):
        ShureSystemAPIClient(base_url="http://shure.test")


def test_sennheiser_client_rejects_cleartext_base_url(monkeypatch) -> None:
    """Basic-auth credentials cannot be configured on cleartext Sennheiser connections."""
    monkeypatch.setattr(
        app_settings,
        "get_config_dict",
        lambda: {
            "SENNHEISER_API_BASE_URL": "http://sennheiser.test",
            "SENNHEISER_API_PASSWORD": "test-secret",
        },
    )

    with pytest.raises(ValueError, match="SENNHEISER_API_BASE_URL must be an absolute HTTPS URL"):
        SennheiserSystemAPIClient()


def test_shure_client_rejects_cleartext_websocket_url(monkeypatch) -> None:
    """Manufacturer event data cannot use a cleartext WebSocket connection."""
    monkeypatch.setattr(
        app_settings,
        "get_config_dict",
        lambda: {
            "SHURE_API_SHARED_KEY": "test-secret",
            "SHURE_API_WEBSOCKET_URL": "ws://shure.test/events",
        },
    )

    with pytest.raises(ValueError, match="SHURE_API_WEBSOCKET_URL must be an absolute WSS URL"):
        ShureSystemAPIClient(base_url="https://shure.test")


def test_resilient_session_uses_httpx_certificate_verification_defaults(monkeypatch) -> None:
    """Shared pooled sessions cannot accept or forward a verification override."""
    client_factory = MagicMock(return_value=MagicMock(spec=httpx.Client))
    monkeypatch.setattr(resilience.httpx, "Client", client_factory)

    session = resilience.create_resilient_session(max_retries=2)

    assert session is client_factory.return_value
    assert "verify" not in client_factory.call_args.kwargs


def test_efis_import_uses_verified_shared_session(monkeypatch) -> None:
    """EFIS imports cannot pass a certificate-verification override to the session."""
    session = MagicMock(spec=httpx.Client)
    session_factory = MagicMock(return_value=session)
    monkeypatch.setattr(efis_import_module, "create_resilient_session", session_factory)
    monkeypatch.setattr(efis_import_module.ActivityLog.objects, "create", MagicMock())
    monkeypatch.setattr(
        efis_import_module.EFISImportService,
        "_fetch_wireless_term_ids",
        MagicMock(return_value={1}),
    )
    monkeypatch.setattr(
        efis_import_module.EFISImportService,
        "_fetch_regions",
        MagicMock(return_value=[]),
    )

    result = efis_import_module.EFISImportService.run_import()

    assert result["success"] is True
    session_factory.assert_called_once_with(max_retries=3)
    assert "verify" not in session_factory.call_args.kwargs
    session.close.assert_called_once_with()


def test_shure_websocket_uses_wss_defaults_and_redacts_handshake(monkeypatch, caplog) -> None:
    """Shure subscriptions rely on WSS verification without logging private identifiers."""
    private_transport_id = "private-transport-id"
    private_device_id = "private-device-id"
    websocket_url = "wss://shure.test/events"

    class FakeWebSocket:
        async def recv(self) -> str:
            return f'{{"transportId": "{private_transport_id}"}}'

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class FakeConnection:
        async def __aenter__(self) -> FakeWebSocket:
            return FakeWebSocket()

        async def __aexit__(self, *exc_info: object) -> None:
            return None

    connect = Mock(return_value=FakeConnection())
    adapted_calls: list[tuple[object, bool]] = []

    def adapt_sync(function, *, thread_sensitive: bool):
        adapted_calls.append((function, thread_sensitive))

        async def invoke(*args, **kwargs):
            return function(*args, **kwargs)

        return invoke

    monkeypatch.setattr(shure_websocket_module, "HAS_WEBSOCKETS", True)
    monkeypatch.setattr(
        shure_websocket_module,
        "websockets",
        SimpleNamespace(connect=connect),
    )
    monkeypatch.setattr(shure_websocket_module, "sync_to_async", adapt_sync)
    client = SimpleNamespace(
        websocket_url=websocket_url,
        _make_request=Mock(return_value={"status": "success"}),
    )

    async def callback(_data: dict[str, str]) -> None:
        return None

    with caplog.at_level(logging.DEBUG, logger="micboard.integrations.shure.websocket"):
        asyncio.run(
            shure_websocket_module.connect_and_subscribe(client, private_device_id, callback)
        )

    connect.assert_called_once_with(websocket_url)
    assert adapted_calls == [(shure_websocket_module._subscribe_client_to_transport, True)]
    assert private_transport_id not in caplog.text
    assert private_device_id not in caplog.text
    assert websocket_url not in caplog.text
