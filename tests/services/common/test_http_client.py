"""Behavioral coverage for the shared HTTP client foundation."""

from __future__ import annotations

import gzip
from collections.abc import Generator
from unittest.mock import Mock, call

import httpx
import pytest

from micboard.exceptions import APIError, APIRateLimitError
from micboard.services.common.base import circuit_breaker as circuit_module
from micboard.services.common.base import client as client_module
from micboard.services.common.base.circuit_breaker import CircuitBreaker
from micboard.services.common.base.client import BaseHTTPClient
from micboard.services.common.network_limits import HTTPClientLimits
from micboard.services.settings.settings_service import settings as app_settings


class DummyAPIError(APIError):
    """Concrete transport error used by the test client."""


class DummyRateLimitError(APIRateLimitError):
    """Concrete rate-limit error used by the test client."""


class DummyHTTPClient(BaseHTTPClient):
    """Small concrete client exposing BaseHTTPClient behavior."""

    def _get_config_prefix(self) -> str:
        return "TEST_API"

    def _get_default_base_url(self) -> str:
        return "https://default.test"

    def _configure_authentication(self, config: dict[str, object]) -> None:
        self.configured = config

    def _get_health_check_endpoint(self) -> str:
        return "/health"

    def get_exception_class(self) -> type[DummyAPIError]:
        return DummyAPIError

    def get_rate_limit_exception_class(self) -> type[DummyRateLimitError]:
        return DummyRateLimitError


@pytest.fixture
def transport_client(monkeypatch) -> Generator[DummyHTTPClient]:
    monkeypatch.setattr(
        app_settings,
        "get_config_dict",
        lambda: {
            "TEST_API_TIMEOUT": 3,
            "TEST_API_MAX_RETRIES": 0,
            "TEST_API_RETRY_BACKOFF": 0,
        },
    )
    client = DummyHTTPClient()
    yield client
    client.close()


def _response(status: int, *, content: bytes = b"", headers: dict[str, str] | None = None):
    return httpx.Response(
        status,
        content=content,
        headers=headers,
        request=httpx.Request("GET", "https://default.test/resource"),
    )


def test_api_error_string_and_retry_header_parsing() -> None:
    response = _response(429, headers={"Retry-After": "12"})
    assert str(APIError("plain")) == "[API_ERROR] plain"
    assert str(APIError("failed", status_code=503)) == "[API_ERROR] failed"
    assert str(APIRateLimitError(response=response)) == "[API_RATE_LIMIT] Rate limit exceeded"
    invalid = APIRateLimitError(response=_response(429, headers={"Retry-After": "later"}))
    assert invalid.retry_after is None
    assert str(invalid) == "[API_RATE_LIMIT] Rate limit exceeded"
    assert APIRateLimitError().retry_after is None


@pytest.mark.parametrize(
    "url",
    [
        "not a url",
        "http://cleartext.test",
        "https:///missing-host",
        "https://user:secret@example.test/api",
        "https://example.test/api?token=secret",
        "https://example.test/api#secret",
        object(),
    ],
)
def test_base_client_rejects_invalid_or_insecure_urls(monkeypatch, url: object) -> None:
    monkeypatch.setattr(app_settings, "get_config_dict", lambda: {})
    with pytest.raises(ValueError, match="absolute HTTPS URL"):
        DummyHTTPClient(base_url=url)  # type: ignore[arg-type]


def test_health_check_reports_healthy_unhealthy_and_transport_error(transport_client) -> None:
    transport_client._send_bounded_request = Mock(
        side_effect=[
            _response(200),
            _response(503),
            httpx.ConnectError("down", request=httpx.Request("GET", "https://default.test")),
        ]
    )

    healthy = transport_client.check_health()
    unhealthy = transport_client.check_health()
    failed = transport_client.check_health()

    assert healthy["status"] == "healthy"
    assert unhealthy["status"] == "unhealthy"
    assert unhealthy["details"]["status_code"] == 503
    assert failed["status"] == "error"
    assert failed["error"] == "Health check failed (ConnectError); details redacted."
    assert "down" not in failed["error"]
    assert transport_client._send_bounded_request.call_args_list == [
        call("GET", "https://default.test/health", timeout=5),
        call("GET", "https://default.test/health", timeout=5),
        call("GET", "https://default.test/health", timeout=5),
    ]


def test_health_check_fails_closed_on_oversized_streamed_body(transport_client) -> None:
    """Health checks stop reading and redact a response that crosses the byte ceiling."""

    class OversizedHealthStream(httpx.SyncByteStream):
        chunks_read = 0

        def __iter__(self):
            self.chunks_read += 1
            yield b"secret-health-body=" + (b"x" * 8192)
            self.chunks_read += 1
            yield b"must-not-be-read"

    stream = OversizedHealthStream()

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream, request=request)

    transport_client.client.close()
    transport_client.client = httpx.Client(transport=httpx.MockTransport(respond))
    transport_client.http_limits = HTTPClientLimits(
        max_retry_delay_seconds=3,
        max_response_bytes=64,
    )

    result = transport_client.check_health()

    assert result["status"] == "error"
    assert result["error"] == "Health check failed (DummyAPIError); details redacted."
    assert "secret-health-body" not in str(result)
    assert stream.chunks_read == 1
    assert not transport_client.is_healthy()


@pytest.mark.parametrize(
    ("transport_error", "message"),
    [
        (
            httpx.ReadTimeout("late", request=httpx.Request("GET", "https://default.test")),
            "Timeout",
        ),
        (
            httpx.ConnectError("down", request=httpx.Request("GET", "https://default.test")),
            "Connection",
        ),
    ],
)
def test_request_wraps_final_transport_errors(
    transport_client, transport_error, message: str
) -> None:
    transport_client._send_bounded_request = Mock(side_effect=transport_error)

    with pytest.raises(DummyAPIError, match=message):
        transport_client._make_request("GET", "/resource")

    assert not transport_client.is_healthy()


def test_request_retries_transport_error_and_honors_retry_after(monkeypatch) -> None:
    monkeypatch.setattr(
        app_settings,
        "get_config_dict",
        lambda: {"TEST_API_MAX_RETRIES": 1, "TEST_API_RETRY_BACKOFF": 0},
    )
    sleep = Mock()
    monkeypatch.setattr(client_module.time, "sleep", sleep)
    client = DummyHTTPClient()
    monkeypatch.setattr(
        client,
        "_send_bounded_request",
        Mock(
            side_effect=[
                httpx.ConnectError("transient", request=httpx.Request("GET", client.base_url)),
                _response(200, content=b'{"ok": true}'),
            ]
        ),
    )
    assert client._make_request("GET", "/resource") == {"ok": True}

    monkeypatch.setattr(
        client,
        "_send_bounded_request",
        Mock(
            side_effect=[
                _response(503, headers={"Retry-After": "2"}),
                _response(200),
            ]
        ),
    )
    assert client._make_request("GET", "/resource") is None
    sleep.assert_called_once_with(2.0)
    client.close()


def test_request_preserves_http_errors_and_handles_unknown_exception(transport_client) -> None:
    transport_client._send_bounded_request = Mock(
        return_value=_response(418, content=b"short failure")
    )
    with pytest.raises(DummyAPIError) as exc_info:
        transport_client._make_request("POST", "/resource")
    assert exc_info.value.status_code == 418

    transport_client._send_bounded_request = Mock(side_effect=RuntimeError("unexpected"))
    with pytest.raises(DummyAPIError, match="Unknown request error") as exc_info:
        transport_client._make_request("GET", "/resource")
    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_rate_limit_and_retry_after_edge_cases(transport_client, monkeypatch) -> None:
    response = _response(429, headers={"Retry-After": "later"})
    transport_client._send_bounded_request = Mock(return_value=response)
    with pytest.raises(DummyRateLimitError) as exc_info:
        transport_client._make_request("GET", "/resource")
    assert exc_info.value.retry_after is None

    assert transport_client._extract_retry_after(_response(200)) is None
    sleep = Mock()
    monkeypatch.setattr(client_module.time, "sleep", sleep)
    transport_client.retry_backoff = 0
    transport_client._sleep_before_retry(2)
    sleep.assert_not_called()


def test_retry_delay_clamps_huge_header_and_backoff(monkeypatch, transport_client) -> None:
    """Untrusted headers and exponential configuration cannot exceed the sleep ceiling."""
    transport_client.http_limits = HTTPClientLimits(
        max_retry_delay_seconds=3,
        max_response_bytes=1024,
    )
    sleep = Mock()
    monkeypatch.setattr(client_module.time, "sleep", sleep)

    transport_client._sleep_before_retry(
        0,
        response=_response(503, headers={"Retry-After": "999999999999"}),
    )
    transport_client.retry_backoff = 1000
    transport_client._sleep_before_retry(1_000_000)

    assert sleep.call_args_list == [call(3.0), call(3.0)]

    transport_client._send_bounded_request = Mock(
        return_value=_response(429, headers={"Retry-After": "999999999999"})
    )
    with pytest.raises(DummyRateLimitError) as exc_info:
        transport_client._make_request("GET", "/resource")
    assert exc_info.value.retry_after == 3


def test_oversized_success_response_fails_before_json_parse(transport_client) -> None:
    """A successful vendor response is byte-checked before JSON allocation."""
    transport_client.http_limits = HTTPClientLimits(
        max_retry_delay_seconds=3,
        max_response_bytes=8,
    )
    response = Mock()
    response.status_code = 200
    response.headers = {}
    response.content = b'{"payload": true}'

    with pytest.raises(DummyAPIError, match="exceeded byte limit"):
        transport_client._handle_response(response, "GET", transport_client.base_url)

    response.json.assert_not_called()
    assert not transport_client.is_healthy()


def test_compressed_response_is_bounded_by_decoded_bytes(transport_client) -> None:
    """A small compressed body cannot expand past the decoded response ceiling."""
    compressed = gzip.compress(b'{"payload":"' + (b"x" * 1024) + b'"}')

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Encoding": "gzip"},
            content=compressed,
            request=request,
        )

    transport_client.client.close()
    transport_client.client = httpx.Client(transport=httpx.MockTransport(respond))
    transport_client.http_limits = HTTPClientLimits(
        max_retry_delay_seconds=3,
        max_response_bytes=64,
    )

    with pytest.raises(DummyAPIError, match="exceeded byte limit"):
        transport_client._make_request("GET", "/resource")


def test_chunked_response_is_bounded_without_content_length(transport_client) -> None:
    """A chunked response is stopped once decoded chunks cross the byte ceiling."""

    class OversizedChunkStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b'{"payload":"'
            yield b"x" * 64
            yield b'"}'

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Transfer-Encoding": "chunked"},
            stream=OversizedChunkStream(),
            request=request,
        )

    transport_client.client.close()
    transport_client.client = httpx.Client(transport=httpx.MockTransport(respond))
    transport_client.http_limits = HTTPClientLimits(
        max_retry_delay_seconds=3,
        max_response_bytes=32,
    )

    with pytest.raises(DummyAPIError, match="exceeded byte limit"):
        transport_client._make_request("GET", "/resource")


def test_circuit_fail_fast_and_metric_transitions(transport_client, monkeypatch) -> None:
    transport_client._circuit.allow_request = Mock(return_value=False)
    with pytest.raises(DummyAPIError) as exc_info:
        transport_client._make_request("GET", "/resource")
    assert exc_info.value.code == "API_CIRCUIT_OPEN"

    metric = Mock()
    monkeypatch.setattr("micboard.metrics.MetricsCollector.record_metric", metric)
    breaker = CircuitBreaker(name="vendor", failure_threshold=1, recovery_timeout=10)
    breaker.record_failure()
    assert breaker.state == "open"
    assert metric.call_args.args[0].method_name == "circuit_open"
    breaker.record_success()
    assert breaker.state == "closed"
    assert metric.call_args.args[0].method_name == "circuit_closed"


def test_circuit_recovery_and_metric_failures_are_nonfatal(monkeypatch) -> None:
    now = iter([100.0, 105.0, 106.0, 116.0])
    monkeypatch.setattr(circuit_module.time, "time", lambda: next(now))
    monkeypatch.setattr(
        "micboard.metrics.MetricsCollector.record_metric",
        Mock(side_effect=RuntimeError("metrics down")),
    )
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=10)
    breaker.record_failure()
    breaker.record_failure()
    assert not breaker.allow_request()
    assert breaker.allow_request()
    assert breaker.state == "half-open"
    breaker.record_success()
    assert breaker.state == "closed"


def test_failure_and_success_ignore_broken_circuit_callbacks(transport_client) -> None:
    transport_client._circuit.record_failure = Mock(side_effect=RuntimeError("breaker down"))
    transport_client._record_request_failure()
    assert transport_client._consecutive_failures == 1

    transport_client._circuit.record_success = Mock(side_effect=RuntimeError("breaker down"))
    assert transport_client._handle_response(_response(204), "GET", "https://default.test") is None
    assert transport_client.is_healthy()


def test_response_without_circuit_and_invalid_json(transport_client) -> None:
    del transport_client._circuit
    transport_client._record_request_failure()
    assert transport_client._consecutive_failures == 1
    assert (
        transport_client._handle_response(_response(204), "GET", transport_client.base_url) is None
    )

    with pytest.raises(DummyAPIError, match="Invalid JSON"):
        transport_client._handle_response(
            _response(200, content=b"not-json"),
            "GET",
            transport_client.base_url,
        )


def test_context_manager_closes_transport(transport_client) -> None:
    transport_client.client.close = Mock()
    with transport_client as entered:
        assert entered is transport_client
    transport_client.client.close.assert_called_once_with()
