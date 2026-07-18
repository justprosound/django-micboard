"""WebSocket support for real-time Shure System API device updates.

⚠️ IMPORTANT: This module is for BACKEND-TO-HARDWARE communication only.

This WebSocket client subscribes to the Shure System API's hardware endpoint
(/api/v1/subscriptions/websocket/create) to receive push notifications when
device state changes (battery levels, RF signal, audio meters, etc.).

This is NOT related to browser WebSockets for the frontend UI. Browser updates
are handled via HTMX polling/SSE, not WebSockets. This module enables the Django
backend to receive real-time telemetry from Shure hardware without constant polling.

Shure System API WebSocket Flow:
1. Connect to wss://{device-ip}:2420/api/v1/subscriptions/websocket/create
2. Receive transportId from initial message
3. POST to /api/v1/devices/{id}/identify/subscription/{transport_id}
4. Receive JSON messages when device state changes
5. Update database and trigger HTMX updates to connected browsers

Optional Dependency:
    This requires the 'websockets' package. Install with:
    uv add "django-micboard[shure]"

See docs/shure-integration.md for full details on Shure System API integration.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import Any, Protocol

from asgiref.sync import sync_to_async

from micboard.utils.exception_logging import sanitized_exception_info

websockets: Any
WebsocketClosedOKError: type[Exception]
WebsocketConnectionClosedError: type[Exception]

try:
    import websockets as websockets_package
    from websockets.exceptions import (
        ConnectionClosedError,
        ConnectionClosedOK,
    )

    websockets = websockets_package
    WebsocketClosedOKError = ConnectionClosedOK
    WebsocketConnectionClosedError = ConnectionClosedError
    HAS_WEBSOCKETS = True
except ImportError:  # pragma: no cover - optional dependency
    websockets = None
    WebsocketClosedOKError = type("WebsocketClosedOKError", (Exception,), {})
    WebsocketConnectionClosedError = type("WebsocketConnectionClosedError", (Exception,), {})


logger = logging.getLogger(__name__)


class ShureWebSocketClient(Protocol):
    """Minimum authenticated client interface needed by the WebSocket adapter."""

    @property
    def websocket_url(self) -> str | None:
        raise NotImplementedError

    def _make_request(self, method: str, endpoint: str) -> Any | None:
        raise NotImplementedError


class ShureWebSocketError(Exception):
    """Exception for WebSocket-related errors."""

    pass


def _parse_transport_id_from_message(message: str | bytes) -> str | None:
    try:
        if isinstance(message, bytes):
            message = message.decode("utf-8")
        payload = json.loads(message)
        return payload.get("transportId")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.exception(
            "Failed to parse WebSocket transport ID message",
            exc_info=sanitized_exception_info(exc),
        )
        return None


def _subscribe_client_to_transport(client: Any, device_id: str, transport_id: str) -> None:
    from .exceptions import ShureAPIError

    subscribe_endpoint = f"/api/v1/devices/{device_id}/identify/subscription/{transport_id}"
    try:
        subscribe_response = client._make_request("POST", subscribe_endpoint)
        if subscribe_response and subscribe_response.get("status") == "success":
            logger.info("Successfully subscribed to Shure device updates")
        else:
            logger.error("Failed to subscribe to Shure device updates")
            raise ShureWebSocketError("Failed to subscribe to Shure device updates")
    except ShureAPIError as exc:
        logger.exception(
            "Error during Shure REST subscription",
            exc_info=sanitized_exception_info(exc),
        )
        raise


async def _read_and_dispatch_messages(
    websocket: Any,
    device_id: str,
    callback: Callable[[dict[str, Any]], Awaitable[None] | None],
) -> None:
    async for message in websocket:
        try:
            data = json.loads(message)
            logger.debug("Received Shure WebSocket message")
            callback_result = callback(data)
            if isawaitable(callback_result):
                await callback_result
        except json.JSONDecodeError as exc:
            logger.exception(
                "Failed to parse Shure WebSocket message",
                exc_info=sanitized_exception_info(exc),
            )
            continue
        except Exception as exc:
            logger.exception(
                "Error processing WebSocket message",
                exc_info=sanitized_exception_info(exc),
            )
            continue


async def connect_and_subscribe(
    client: ShureWebSocketClient,
    device_id: str,
    callback: Callable[[dict[str, Any]], Awaitable[None] | None],
) -> None:
    """Establishes WebSocket connection and subscribes to device updates.

    Args:
        client: ShureSystemAPIClient instance
        device_id: The Shure API device ID to subscribe to
        callback: Function to call with received WebSocket messages

    Raises:
        ShureWebSocketError: If connection or subscription fails
    """
    from .exceptions import ShureAPIError

    if not HAS_WEBSOCKETS or not websockets:
        logger.error(
            "websockets dependency not installed; install django-micboard[websocket] to enable"
        )
        raise ShureWebSocketError(
            "websockets dependency missing; install django-micboard[websocket] to enable"
        )

    if not client.websocket_url:
        logger.error("Shure API WebSocket URL not configured")
        raise ShureWebSocketError("Shure API WebSocket URL not configured")

    try:
        async with websockets.connect(client.websocket_url) as websocket:
            logger.info("Connected to Shure API WebSocket")

            # Read initial message and extract transportId
            message = await websocket.recv()
            logger.debug("Received initial Shure WebSocket handshake")

            transport_id = _parse_transport_id_from_message(message)
            if not transport_id:
                logger.error("Missing transport ID in Shure WebSocket handshake")
                raise ShureWebSocketError("Failed to get transportId from WebSocket")

            logger.info("Received Shure WebSocket transport ID")

            # Subscribe via REST
            await sync_to_async(
                _subscribe_client_to_transport,
                thread_sensitive=True,
            )(client, device_id, transport_id)

            # Continuously receive messages and dispatch to callback
            await _read_and_dispatch_messages(websocket, device_id, callback)

    except WebsocketClosedOKError:
        logger.info("Shure API WebSocket connection closed gracefully")
    except WebsocketConnectionClosedError as exc:
        logger.exception(
            "Shure API WebSocket connection closed with error",
            exc_info=sanitized_exception_info(exc),
        )
        raise ShureWebSocketError("Shure WebSocket connection error") from None
    except ShureWebSocketError:
        raise
    except ShureAPIError:
        raise
    except Exception as exc:
        logger.exception(
            "Unhandled error in Shure API WebSocket connection",
            exc_info=sanitized_exception_info(exc),
        )
        raise ShureWebSocketError("Unhandled Shure WebSocket error") from None
