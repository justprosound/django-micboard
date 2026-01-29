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
    pip install django-micboard[websocket]

See docs/shure-integration.md for full details on Shure System API integration.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Callable

try:
    import websockets

    HAS_WEBSOCKETS = True
    WebsocketClosedOKError = websockets.exceptions.ConnectionClosedOK
    WebsocketConnectionClosedError = websockets.exceptions.ConnectionClosedError
except ImportError:  # pragma: no cover - optional dependency
    websockets = None
    HAS_WEBSOCKETS = False

    class WebsocketClosedOKError(Exception):
        """Placeholder when websockets is unavailable."""

    class WebsocketConnectionClosedError(Exception):
        """Placeholder when websockets is unavailable."""


if TYPE_CHECKING:
    from .client import ShureSystemAPIClient

logger = logging.getLogger(__name__)


class ShureWebSocketError(Exception):
    """Exception for WebSocket-related errors."""

    pass


async def connect_and_subscribe(
    client: ShureSystemAPIClient,
    device_id: str,
    callback: Callable[[dict], None],
) -> None:
    """Establishes WebSocket connection and subscribes to device updates.

    Args:
        client: ShureSystemAPIClient instance
        device_id: The Shure API device ID to subscribe to
        callback: Function to call with received WebSocket messages

    Raises:
        ShureWebSocketError: If connection or subscription fails
    """
    from .client import ShureAPIError

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
        async with websockets.connect(client.websocket_url, ssl=client.verify_ssl) as websocket:
            logger.info("Connected to Shure API WebSocket: %s", client.websocket_url)

            # First message from WebSocket is usually the transportId
            message = await websocket.recv()
            logger.debug("Received initial WebSocket message: %s", message[:200])

            try:
                transport_id_data = json.loads(message)
                transport_id = transport_id_data.get("transportId")
            except json.JSONDecodeError:
                logger.exception("Failed to parse WebSocket transport ID message")
                raise ShureWebSocketError("Invalid WebSocket transport ID message") from None

            if not transport_id:
                logger.error("Missing transportId in WebSocket message: %s", message[:200])
                raise ShureWebSocketError("Failed to get transportId from WebSocket")

            logger.info("Received transportId: %s", transport_id)

            # Subscribe to device updates using the REST API with the transportId
            subscribe_endpoint = f"/api/v1/devices/{device_id}/identify/subscription/{transport_id}"
            try:
                # This is a POST request to the REST API, not over the WebSocket
                subscribe_response = client._make_request("POST", subscribe_endpoint)
                if subscribe_response and subscribe_response.get("status") == "success":
                    logger.info("Successfully subscribed to device %s updates", device_id)
                else:
                    logger.error(
                        "Failed to subscribe to device %s: %s",
                        device_id,
                        subscribe_response,
                    )
                    raise ShureWebSocketError(f"Failed to subscribe to device {device_id} updates")
            except ShureAPIError:
                logger.exception("Error during REST subscription for device %s", device_id)
                raise

            # Continuously receive messages from the WebSocket
            async for message in websocket:
                try:
                    data = json.loads(message)
                    logger.debug("Received WebSocket message for device %s", device_id)
                    callback(data)  # Pass the received data to the callback
                except json.JSONDecodeError:
                    logger.exception("Failed to parse WebSocket message: %s", message[:200])
                    continue  # Skip invalid messages but keep connection alive
                except Exception:
                    logger.exception("Error processing WebSocket message")
                    continue  # Don't let callback errors kill the connection

    except WebsocketClosedOKError:
        logger.info("Shure API WebSocket connection closed gracefully for device %s", device_id)
    except WebsocketConnectionClosedError:
        logger.exception(
            "Shure API WebSocket connection closed with error for device %s", device_id
        )
        raise ShureWebSocketError(f"WebSocket connection error for device {device_id}") from None
    except ShureWebSocketError:
        # Re-raise ShureWebSocketError exceptions (they're already properly formatted)
        raise
    except ShureAPIError:
        # Re-raise ShureAPIError exceptions (they should propagate up)
        raise
    except Exception:
        logger.exception(
            "Unhandled error in Shure API WebSocket connection for device %s",
            device_id,
        )
        raise ShureWebSocketError(f"Unhandled WebSocket error for device {device_id}") from None
