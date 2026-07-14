"""SSE client for Sennheiser SSCv2 subscriptions."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

import httpx
from asgiref.sync import sync_to_async

from micboard.services.common.network_limits import (
    SSE_READ_CHUNK_BYTES,
    SSEStreamLimits,
)

from .exceptions import SennheiserAPIError

logger = logging.getLogger(__name__)


class SSEClient(Protocol):
    base_url: str
    password: str

    def _make_request(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        raise NotImplementedError


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
    # Start subscription
    try:
        response = await sync_to_async(
            client._make_request,
            thread_sensitive=True,
        )("GET", "/api/ssc/state/subscriptions")
        if not response or not isinstance(response, dict):
            raise SennheiserAPIError("SSE subscription did not return a session")

        session_uuid = response.get("sessionUUID")
        if not session_uuid:
            raise SennheiserAPIError("SSE subscription response omitted its session identifier")

        logger.info("Started Sennheiser event subscription")

        # Subscribe to device resources
        resources = [f"/api/devices/{device_id}"]
        await sync_to_async(
            client._make_request,
            thread_sensitive=True,
        )(
            "PUT",
            f"/api/ssc/state/subscriptions/{session_uuid}",
            json=resources,
        )

        # Start SSE stream
        sse_url = f"{client.base_url}/api/ssc/state/subscriptions/{session_uuid}"
        headers = {"Authorization": f"Bearer {client.password}"}

        timeout = httpx.Timeout(connect=10, read=None, write=10, pool=10)
        async with (
            httpx.AsyncClient(
                headers=headers,
                timeout=timeout,
            ) as stream_client,
            stream_client.stream("GET", sse_url) as stream_response,
        ):
            if stream_response.status_code != 200:
                logger.error(
                    "SSE connection failed with status %d",
                    stream_response.status_code,
                )
                return

            limits = SSEStreamLimits.from_settings()
            async for line in _iter_bounded_sse_lines(
                stream_response,
                max_line_bytes=limits.max_line_bytes,
            ):
                await _dispatch_sse_event(
                    line,
                    callback=callback,
                    max_event_bytes=limits.max_event_bytes,
                )

    except SennheiserAPIError:
        logger.exception("Sennheiser event subscription failed")
        raise
    except Exception:
        logger.exception("Sennheiser event subscription failed")
        raise SennheiserAPIError("Sennheiser event subscription failed") from None


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
