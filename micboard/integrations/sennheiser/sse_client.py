"""SSE client for Sennheiser SSCv2 subscriptions."""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)


class SSEClient(Protocol):
    base_url: str
    password: str

    def _make_request(self, method: str, endpoint: str, **kwargs: Any) -> Any: ...


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
        response = client._make_request("GET", "/api/ssc/state/subscriptions")
        if not response or not isinstance(response, dict):
            logger.error("Failed to start subscription")
            return

        session_uuid = response.get("sessionUUID")
        if not session_uuid:
            logger.error("No sessionUUID in subscription response")
            return

        logger.info("Started Sennheiser event subscription")

        # Subscribe to device resources
        resources = [f"/api/devices/{device_id}"]
        client._make_request("PUT", f"/api/ssc/state/subscriptions/{session_uuid}", json=resources)

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

            async for line in stream_response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                data_str = line[6:]
                try:
                    data = json.loads(data_str)
                    await callback(data)
                except json.JSONDecodeError:
                    logger.debug("Invalid JSON in SSE event data")

    except Exception:
        logger.error("Sennheiser event subscription failed")
