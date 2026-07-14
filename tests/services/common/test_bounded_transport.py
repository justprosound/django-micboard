"""Focused contracts for the bounded synchronous HTTP transport adapter."""

from __future__ import annotations

import httpx
import pytest

from micboard.services.common.base.bounded_transport import BoundedHTTPTransport
from micboard.services.common.network_limits import HTTPClientLimits


class OversizedResponseError(RuntimeError):
    """Test-only signal raised by the owning API client's failure callback."""


def _raise_oversized(method: str) -> None:
    raise OversizedResponseError(method)


def _transport(client: httpx.Client, *, max_response_bytes: int = 64) -> BoundedHTTPTransport:
    return BoundedHTTPTransport(
        client=client,
        limits=HTTPClientLimits(
            max_retry_delay_seconds=3,
            max_response_bytes=max_response_bytes,
        ),
        oversized_response=_raise_oversized,
    )


def test_send_returns_decoded_bounded_response_with_request_metadata() -> None:
    """Successful streams are rebuilt as buffered responses for JSON consumers."""

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"X-Vendor": "test"},
            json={"status": "ok"},
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        response = _transport(client).send("GET", "https://vendor.test/status")

    assert response.json() == {"status": "ok"}
    assert response.headers["X-Vendor"] == "test"
    assert response.request.url == httpx.URL("https://vendor.test/status")


def test_error_response_is_returned_without_reading_untrusted_body() -> None:
    """Error bodies remain unread because callers redact them before raising."""

    class UnreadableErrorBody(httpx.SyncByteStream):
        def __iter__(self):
            raise AssertionError("error body must not be read")

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            stream=UnreadableErrorBody(),
            request=request,
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        response = _transport(client).send("POST", "https://vendor.test/status")

    assert response.status_code == 503


def test_cached_content_enforces_declared_and_actual_byte_limits() -> None:
    """Buffered response handling uses the same declared and actual byte ceilings."""
    with httpx.Client() as client:
        transport = _transport(client, max_response_bytes=8)
        invalid_length = httpx.Response(
            200,
            content=b"short",
            headers={"Content-Length": "invalid"},
        )
        assert transport.response_content(invalid_length, method="GET") == b"short"

        declared_oversized = httpx.Response(
            200,
            content=b"short",
            headers={"Content-Length": "9"},
        )
        with pytest.raises(OversizedResponseError, match="GET"):
            transport.response_content(declared_oversized, method="GET")

        actual_oversized = httpx.Response(200, content=b"ninebytes")
        del actual_oversized.headers["Content-Length"]
        with pytest.raises(OversizedResponseError, match="POST"):
            transport.response_content(actual_oversized, method="POST")


@pytest.mark.parametrize(
    ("header", "expected"),
    [(None, None), ("invalid", None), ("0", None), ("2", 2), ("999", 3)],
)
def test_retry_after_parsing_is_positive_and_bounded(
    header: str | None,
    expected: int | None,
) -> None:
    """Untrusted retry headers cannot make callers sleep beyond their ceiling."""
    headers = {"Retry-After": header} if header is not None else {}
    response = httpx.Response(503, headers=headers)
    with httpx.Client() as client:
        assert _transport(client).extract_retry_after(response) == expected
