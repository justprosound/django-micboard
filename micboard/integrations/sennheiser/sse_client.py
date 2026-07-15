"""SSE client for Sennheiser SSCv2 subscriptions."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

import httpx

from micboard.services.common.network_limits import (
    SSE_READ_CHUNK_BYTES,
    SSEStreamLimits,
)
from micboard.utils.exception_logging import sanitized_exception_info

from .exceptions import SennheiserAPIError

logger = logging.getLogger(__name__)


class SSEClient(Protocol):
    base_url: str
    username: str
    password: str


async def connect_and_subscribe(
    client: SSEClient,
    device_id: str,
    callback: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    """Establish SSE connection and subscribe to Sennheiser device updates.

    Args:
        client: SennheiserSystemAPIClient instance
        device_id: The Sennheiser API device ID to subscribe to
        callback: Function to call with received SSE messages
    """
    try:
        await _connect_and_subscribe(client, device_id=device_id, callback=callback)

    except SennheiserAPIError as exc:
        logger.exception(
            "Sennheiser event subscription failed",
            exc_info=sanitized_exception_info(exc),
        )
        raise
    except Exception as exc:
        logger.exception(
            "Sennheiser event subscription failed",
            exc_info=sanitized_exception_info(exc),
        )
        raise SennheiserAPIError("Sennheiser event subscription failed") from None


async def _connect_and_subscribe(
    client: SSEClient,
    *,
    device_id: str,
    callback: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    """Open the SSCv2 stream and configure its resources on a control connection."""
    timeout = httpx.Timeout(connect=10, read=None, write=10, pool=10)
    authentication = httpx.BasicAuth(client.username, client.password)
    subscription_url = f"{client.base_url}/api/ssc/state/subscriptions"
    async with (
        httpx.AsyncClient(auth=authentication, timeout=timeout) as stream_client,
        httpx.AsyncClient(auth=authentication, timeout=timeout) as control_client,
        stream_client.stream(
            "GET",
            subscription_url,
            headers={"Accept": "text/event-stream"},
        ) as stream_response,
    ):
        if stream_response.status_code != 200:
            raise SennheiserAPIError(
                f"SSE subscription failed with status {stream_response.status_code}"
            )
        content_type = stream_response.headers.get("Content-Type", "").partition(";")[0]
        if content_type.strip().lower() != "text/event-stream":
            raise SennheiserAPIError("SSE subscription returned an invalid content type")

        control_url = _subscription_control_url(
            base_url=client.base_url,
            content_location=stream_response.headers.get("Content-Location"),
        )
        control_response = await control_client.put(
            control_url,
            json=[f"/api/devices/{device_id}"],
        )
        if not 200 <= control_response.status_code < 300:
            raise SennheiserAPIError(
                f"SSE resource subscription failed with status {control_response.status_code}"
            )

        logger.info("Started Sennheiser event subscription")
        await _consume_sse_messages(stream_response, callback=callback)


async def _consume_sse_messages(
    response: httpx.Response,
    *,
    callback: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    """Dispatch message events while ignoring SSCv2 open and close metadata."""
    limits = SSEStreamLimits.from_settings()
    event_type = "message"
    async for line in _iter_bounded_sse_lines(
        response,
        max_line_bytes=limits.max_line_bytes,
    ):
        if line.startswith(b"event:"):
            event_type = line[6:].strip().decode("ascii", errors="ignore")
            if event_type == "close":
                break
            continue
        if not line:
            event_type = "message"
            continue
        if event_type in {"", "message"}:
            await _dispatch_sse_event(
                line,
                callback=callback,
                max_event_bytes=limits.max_event_bytes,
            )


def _subscription_control_url(*, base_url: str, content_location: str | None) -> str:
    """Validate and resolve the same-origin SSCv2 subscription control URL."""
    if not content_location:
        raise SennheiserAPIError("SSE subscription omitted Content-Location")

    base = httpx.URL(base_url)
    try:
        control_url = base.join(content_location)
    except (TypeError, httpx.InvalidURL) as exc:
        raise SennheiserAPIError("SSE subscription returned an invalid Content-Location") from exc

    if (
        control_url.scheme != base.scheme
        or control_url.host != base.host
        or control_url.port != base.port
        or control_url.query
        or control_url.fragment
    ):
        raise SennheiserAPIError("SSE subscription returned a cross-origin Content-Location")

    path_parts = control_url.path.removeprefix("/").split("/")
    if len(path_parts) != 5 or path_parts[:4] != ["api", "ssc", "state", "subscriptions"]:
        raise SennheiserAPIError("SSE subscription returned an invalid control path")
    if not path_parts[-1]:
        raise SennheiserAPIError("SSE subscription omitted its session identifier")
    return str(control_url)


async def _iter_bounded_sse_lines(
    response: httpx.Response,
    *,
    max_line_bytes: int,
) -> AsyncIterator[bytes]:
    """Yield SSE lines without retaining an over-limit vendor-controlled line."""
    line_buffer = bytearray()
    discarding_line = False

    async for chunk in response.aiter_bytes(chunk_size=SSE_READ_CHUNK_BYTES):
        segments = chunk.split(b"\n")
        for index, segment in enumerate(segments):
            line_complete = index < len(segments) - 1
            if not discarding_line:
                if len(line_buffer) + len(segment) > max_line_bytes:
                    line_buffer.clear()
                    discarding_line = True
                else:
                    line_buffer.extend(segment)

            if not line_complete:
                continue

            if discarding_line:
                logger.warning("Discarded SSE line that exceeded the byte limit")
            else:
                line = bytes(line_buffer)
                yield line[:-1] if line.endswith(b"\r") else line
            line_buffer.clear()
            discarding_line = False

    if discarding_line:
        logger.warning("Discarded SSE line that exceeded the byte limit")
    elif line_buffer:
        line = bytes(line_buffer)
        yield line[:-1] if line.endswith(b"\r") else line


async def _dispatch_sse_event(
    line: bytes,
    *,
    callback: Callable[[dict[str, Any]], Awaitable[None]],
    max_event_bytes: int,
) -> None:
    """Decode and dispatch one bounded single-line SSE data event."""
    if not line.startswith(b"data: "):
        return

    event_data = line[6:]
    if len(event_data) > max_event_bytes:
        logger.warning("Discarded SSE event data that exceeded the byte limit")
        return
    try:
        data = json.loads(event_data)
        await callback(data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.debug("Invalid JSON in SSE event data")
