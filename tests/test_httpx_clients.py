"""Regression tests for Micboard's httpx-only network boundary."""

from __future__ import annotations

import asyncio
import logging
from functools import partial
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

import micboard.integrations.sennheiser.sse_client as sennheiser_sse_module
from micboard.integrations.sennheiser.client import SennheiserSystemAPIClient
from micboard.integrations.sennheiser.exceptions import SennheiserAPIError
from micboard.integrations.sennheiser.plugin import SennheiserPlugin
from micboard.integrations.shure.client import ShureSystemAPIClient
from micboard.integrations.shure.exceptions import ShureAPIError, ShureAPIRateLimitError
from micboard.integrations.shure.plugin import ShurePlugin
from micboard.services.common.base.plugin import ManufacturerPlugin
from micboard.services.settings.settings_service import settings as app_settings


def _adapt_sync_immediately(
    adapted_calls: list[tuple[object, bool]],
    function,
    *,
    thread_sensitive: bool,
):
    """Record a sync adapter boundary while keeping this unit test deterministic."""
    adapted_calls.append((function, thread_sensitive))

    async def invoke(*args, **kwargs):
        return function(*args, **kwargs)

    return invoke


@pytest.mark.parametrize(
    "client_class",
    [ShureSystemAPIClient, SennheiserSystemAPIClient],
)
@pytest.mark.parametrize(
    "method_name",
    [
        "get_devices",
        "get_device",
        "get_device_channels",
        "get_transmitter_data",
        "get_device_identity",
        "get_device_network",
        "get_device_status",
        "_enrich_device_data",
        "add_discovery_ips",
        "get_discovery_ips",
        "remove_discovery_ips",
    ],
)
def test_system_clients_do_not_expose_subclient_delegations(
    client_class: type[ShureSystemAPIClient] | type[SennheiserSystemAPIClient],
    method_name: str,
) -> None:
    """Device and discovery operations stay on their composed sub-clients."""
    assert not hasattr(client_class, method_name)


@pytest.mark.parametrize("plugin_class", [ShurePlugin, SennheiserPlugin])
def test_builtin_plugins_implement_full_manufacturer_contract(
    plugin_class: type[ShurePlugin] | type[SennheiserPlugin],
) -> None:
    """Built-in discovery services can rely on the typed plugin boundary."""
    assert issubclass(plugin_class, ManufacturerPlugin)
    assert not plugin_class.__abstractmethods__


def test_shure_client_configures_httpx_digest_auth_and_request(monkeypatch) -> None:
    config = {
        "SHURE_API_SHARED_KEY": "test-secret",
        "SHURE_API_USE_DIGEST": True,
    }
    monkeypatch.setattr(app_settings, "get_config_dict", lambda: config)

    with ShureSystemAPIClient(base_url="https://shure.test") as client:
        assert client.client.headers["x-api-key"] == "test-secret"
        assert isinstance(client.client.auth, httpx.DigestAuth)

        response = httpx.Response(
            200,
            json={"status": "ok"},
            request=httpx.Request("GET", "https://shure.test/api/v1/devices"),
        )
        request = Mock(return_value=response)
        monkeypatch.setattr(client, "_send_bounded_request", request)

        assert client._make_request("GET", "/api/v1/devices") == {"status": "ok"}
        assert "verify" not in request.call_args.kwargs


def test_shure_client_preserves_rate_limit_exception(monkeypatch) -> None:
    """A final 429 must retain its typed exception and Retry-After metadata."""
    monkeypatch.setattr(
        app_settings,
        "get_config_dict",
        lambda: {
            "SHURE_API_SHARED_KEY": "test-secret",
            "SHURE_API_MAX_RETRIES": 0,
        },
    )

    with ShureSystemAPIClient(base_url="https://shure.test") as client:
        response = httpx.Response(
            429,
            headers={"Retry-After": "7"},
            request=httpx.Request("GET", "https://shure.test/api/v1/devices"),
        )
        monkeypatch.setattr(client, "_send_bounded_request", Mock(return_value=response))

        with pytest.raises(ShureAPIRateLimitError) as exc_info:
            client._make_request("GET", "/api/v1/devices")

    assert exc_info.value.status_code == 429
    assert exc_info.value.retry_after == 7
    assert exc_info.value.response is response


def test_shure_client_retries_retryable_server_error(monkeypatch) -> None:
    """Retryable 5xx responses should be retried before returning success."""
    monkeypatch.setattr(
        app_settings,
        "get_config_dict",
        lambda: {
            "SHURE_API_SHARED_KEY": "test-secret",
            "SHURE_API_MAX_RETRIES": 2,
            "SHURE_API_RETRY_BACKOFF": 0,
        },
    )

    responses = [
        httpx.Response(
            503,
            request=httpx.Request("GET", "https://shure.test/api/v1/devices"),
        ),
        httpx.Response(
            503,
            request=httpx.Request("GET", "https://shure.test/api/v1/devices"),
        ),
        httpx.Response(
            200,
            json={"status": "ok"},
            request=httpx.Request("GET", "https://shure.test/api/v1/devices"),
        ),
    ]

    with ShureSystemAPIClient(base_url="https://shure.test") as client:
        request = Mock(side_effect=responses)
        monkeypatch.setattr(client, "_send_bounded_request", request)

        assert client._make_request("GET", "/api/v1/devices") == {"status": "ok"}

    assert request.call_count == 3
    assert client.is_healthy()


def test_shure_client_wraps_invalid_json_response(monkeypatch) -> None:
    """Successful HTTP responses with invalid JSON must use the canonical API error."""
    monkeypatch.setattr(
        app_settings,
        "get_config_dict",
        lambda: {
            "SHURE_API_SHARED_KEY": "test-secret",
            "SHURE_API_MAX_RETRIES": 0,
        },
    )

    response = httpx.Response(
        200,
        content=b"not-json",
        request=httpx.Request("GET", "https://shure.test/api/v1/devices"),
    )
    with ShureSystemAPIClient(base_url="https://shure.test") as client:
        monkeypatch.setattr(client, "_send_bounded_request", Mock(return_value=response))

        with pytest.raises(ShureAPIError) as exc_info:
            client._make_request("GET", "/api/v1/devices")

    assert exc_info.value.response is response
    assert not client.is_healthy()


def test_sennheiser_client_configures_httpx_basic_auth(monkeypatch) -> None:
    monkeypatch.setattr(
        app_settings,
        "get_config_dict",
        lambda: {"SENNHEISER_API_PASSWORD": "test-password"},
    )

    with SennheiserSystemAPIClient() as client:
        assert isinstance(client.client.auth, httpx.BasicAuth)


def test_sennheiser_sse_stream_uses_async_httpx(monkeypatch, caplog) -> None:
    received: list[dict[str, str]] = []
    client_options: list[dict[str, object]] = []
    adapted_calls: list[tuple[object, bool]] = []
    password_value = "test-credential"

    class FakeStreamResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info: object) -> None:
            return None

        async def aiter_bytes(self, chunk_size: int):
            assert chunk_size == 8192
            for line in (
                b'data: {"state": "online"}\n',
                b"data: not-json\n",
                b"event: ping\n",
            ):
                yield line

    class FakeAsyncClient:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            client_options.append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info: object) -> None:
            return None

        def stream(self, method: str, url: str) -> FakeStreamResponse:
            assert method == "GET"
            assert url.endswith("/session-123")
            return FakeStreamResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    responses = iter([{"sessionUUID": "session-123"}, None])

    monkeypatch.setattr(
        sennheiser_sse_module,
        "sync_to_async",
        partial(_adapt_sync_immediately, adapted_calls),
    )
    client = SimpleNamespace(
        base_url="https://sennheiser.test",
        password=password_value,
        _make_request=Mock(side_effect=responses),
    )

    async def callback(data: dict[str, str]) -> None:
        received.append(data)

    with caplog.at_level(logging.DEBUG, logger="micboard.integrations.sennheiser.sse_client"):
        asyncio.run(sennheiser_sse_module.connect_and_subscribe(client, "device-1", callback))

    assert received == [{"state": "online"}]
    assert adapted_calls == [(client._make_request, True), (client._make_request, True)]
    assert len(client_options) == 1
    assert "verify" not in client_options[0]
    assert "session-123" not in caplog.text
    assert password_value not in caplog.text
    assert "not-json" not in caplog.text


def test_sse_line_reader_discards_chunked_newline_free_overflow(caplog) -> None:
    """A hostile line is never retained past its cap, even across many chunks."""

    class ChunkedResponse:
        async def aiter_bytes(self, chunk_size: int):
            assert chunk_size == 8192
            yield b"data: "
            yield b"x" * 8
            yield b"x" * 8
            yield b"\n"
            yield b"data: {}\r\n"
            yield b"tail"

    async def collect_lines() -> list[bytes]:
        return [
            line
            async for line in sennheiser_sse_module._iter_bounded_sse_lines(
                ChunkedResponse(),  # type: ignore[arg-type]
                max_line_bytes=12,
            )
        ]

    with caplog.at_level(logging.WARNING, logger=sennheiser_sse_module.__name__):
        lines = asyncio.run(collect_lines())

    assert lines == [b"data: {}", b"tail"]
    assert "exceeded the byte limit" in caplog.text


def test_sse_line_reader_discards_newline_free_overflow_at_eof(caplog) -> None:
    """An unterminated oversized stream is dropped without yielding retained payload data."""

    class NewlineFreeResponse:
        async def aiter_bytes(self, chunk_size: int):
            assert chunk_size == 8192
            yield b"data: "
            yield b"x" * 32

    async def collect_lines() -> list[bytes]:
        return [
            line
            async for line in sennheiser_sse_module._iter_bounded_sse_lines(
                NewlineFreeResponse(),  # type: ignore[arg-type]
                max_line_bytes=12,
            )
        ]

    with caplog.at_level(logging.WARNING, logger=sennheiser_sse_module.__name__):
        lines = asyncio.run(collect_lines())

    assert lines == []
    assert "exceeded the byte limit" in caplog.text


def test_sse_event_dispatch_rejects_oversized_payload_before_json_decode(caplog) -> None:
    """The event budget applies independently inside an accepted bounded line."""
    callback = AsyncMock()

    with caplog.at_level(logging.WARNING, logger=sennheiser_sse_module.__name__):
        asyncio.run(
            sennheiser_sse_module._dispatch_sse_event(
                b'data: {"secret":"vendor-payload"}',
                callback=callback,
                max_event_bytes=8,
            )
        )

    callback.assert_not_awaited()
    assert "vendor-payload" not in caplog.text
    assert "exceeded the byte limit" in caplog.text


def test_sennheiser_sse_missing_session_propagates_connection_failure(monkeypatch) -> None:
    """A failed handshake must let connection tracking leave its connecting state."""
    adapted_calls: list[tuple[object, bool]] = []
    monkeypatch.setattr(
        sennheiser_sse_module,
        "sync_to_async",
        partial(_adapt_sync_immediately, adapted_calls),
    )
    client = SimpleNamespace(
        base_url="https://sennheiser.test",
        password="test-credential",
        _make_request=Mock(return_value={}),
    )

    with pytest.raises(SennheiserAPIError, match="did not return a session"):
        asyncio.run(sennheiser_sse_module.connect_and_subscribe(client, "device-1", AsyncMock()))

    assert adapted_calls == [(client._make_request, True)]
