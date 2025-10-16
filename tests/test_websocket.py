"""
Tests for Shure WebSocket functionality.
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from django.test import TestCase
from websockets.exceptions import ConnectionClosedOK

from micboard.manufacturers.shure.client import ShureAPIError, ShureSystemAPIClient
from micboard.manufacturers.shure.websocket import ShureWebSocketError, connect_and_subscribe


class ShureWebSocketTest(TestCase):
    """Test Shure WebSocket functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.client = ShureSystemAPIClient()
        self.client.websocket_url = "ws://test.websocket.url"
        self.client.verify_ssl = True

    async def test_connect_and_subscribe_success(self):
        """Test successful WebSocket connection and subscription."""
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__ = AsyncMock(return_value=mock_websocket)
        mock_websocket.__aexit__ = AsyncMock(return_value=None)

        # Mock the initial transportId message and device messages
        transport_message = {"transportId": "test-transport-123"}
        device_message = {"device": "test-device", "status": "online"}

        # Create a proper async iterator for the websocket
        messages = [json.dumps(transport_message), json.dumps(device_message)]

        async def mock_recv():
            if not messages:
                raise ConnectionClosedOK(None, None)
            return messages.pop(0)

        mock_websocket.recv = mock_recv
        mock_websocket.__aiter__ = Mock(return_value=mock_websocket)

        async def mock_anext(self):
            try:
                return await self.recv()
            except ConnectionClosedOK as err:
                raise StopAsyncIteration from err

        mock_websocket.__anext__ = mock_anext

        callback = Mock()

        with patch(
            "micboard.manufacturers.shure.websocket.websockets.connect", return_value=mock_websocket
        ) as mock_connect:
            with patch.object(self.client, "_make_request") as mock_request:
                mock_request.return_value = {"status": "success"}

                # The connection should close gracefully without raising an exception
                await connect_and_subscribe(self.client, "device1", callback)

                # Verify WebSocket connection was made
                mock_connect.assert_called_once_with("ws://test.websocket.url", ssl=True)

                # Verify subscription request was made
                mock_request.assert_called_once_with(
                    "POST", "/api/v1/devices/device1/identify/subscription/test-transport-123"
                )

                # Verify callback was called with device message
                callback.assert_called_once_with(device_message)

    async def test_connect_and_subscribe_no_websocket_url(self):
        """Test WebSocket connection with no configured URL."""
        self.client.websocket_url = None
        callback = Mock()

        with pytest.raises(ShureWebSocketError, match="Shure API WebSocket URL not configured"):
            await connect_and_subscribe(self.client, "device1", callback)

    async def test_connect_and_subscribe_invalid_transport_message(self):
        """Test WebSocket connection with invalid transport message."""
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__ = AsyncMock(return_value=mock_websocket)
        mock_websocket.__aexit__ = AsyncMock(return_value=None)

        # Mock invalid JSON transport message
        mock_websocket.recv = AsyncMock(return_value="invalid json")

        callback = Mock()

        with patch(
            "micboard.manufacturers.shure.websocket.websockets.connect", return_value=mock_websocket
        ):
            with pytest.raises(ShureWebSocketError, match="Invalid WebSocket transport ID message"):
                await connect_and_subscribe(self.client, "device1", callback)

    async def test_connect_and_subscribe_missing_transport_id(self):
        """Test WebSocket connection with missing transport ID."""
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__ = AsyncMock(return_value=mock_websocket)
        mock_websocket.__aexit__ = AsyncMock(return_value=None)

        # Mock transport message without transportId
        transport_message = {"someOtherField": "value"}
        mock_websocket.recv = AsyncMock(return_value=json.dumps(transport_message))

        callback = Mock()

        with patch(
            "micboard.manufacturers.shure.websocket.websockets.connect", return_value=mock_websocket
        ):
            with pytest.raises(
                ShureWebSocketError, match="Failed to get transportId from WebSocket"
            ):
                await connect_and_subscribe(self.client, "device1", callback)

    async def test_connect_and_subscribe_subscription_failure(self):
        """Test WebSocket connection with subscription failure."""
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__ = AsyncMock(return_value=mock_websocket)
        mock_websocket.__aexit__ = AsyncMock(return_value=None)

        # Mock transport message
        transport_message = {"transportId": "test-transport-123"}
        mock_websocket.recv = AsyncMock(return_value=json.dumps(transport_message))

        callback = Mock()

        with patch(
            "micboard.manufacturers.shure.websocket.websockets.connect", return_value=mock_websocket
        ):
            with patch.object(self.client, "_make_request") as mock_request:
                mock_request.side_effect = ShureAPIError("Subscription failed")

            with pytest.raises(ShureAPIError, match="Subscription failed"):
                await connect_and_subscribe(self.client, "device1", callback)

    async def test_connect_and_subscribe_invalid_device_message(self):
        """Test WebSocket connection with invalid device message JSON."""
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__ = AsyncMock(return_value=mock_websocket)
        mock_websocket.__aexit__ = AsyncMock(return_value=None)

        # Mock transport message and invalid device message
        # messages = [json.dumps({"transportId": "test-transport-123"}), "invalid json message"]

        # Create a proper async iterator for the websocket
        async def mock_anext(self):
            try:
                return await self.recv()
            except ConnectionClosedOK as err:
                raise StopAsyncIteration from err

        mock_websocket.__anext__ = mock_anext

        callback = Mock()

        with patch(
            "micboard.manufacturers.shure.websocket.websockets.connect", return_value=mock_websocket
        ):
            with patch.object(self.client, "_make_request") as mock_request:
                mock_request.return_value = {"status": "success"}

                # The connection should close gracefully without raising an exception
                await connect_and_subscribe(self.client, "device1", callback)

                # Verify callback was not called due to invalid JSON
                callback.assert_not_called()

    async def test_connect_and_subscribe_callback_exception(self):
        """Test WebSocket connection with callback exception."""
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__ = AsyncMock(return_value=mock_websocket)
        mock_websocket.__aexit__ = AsyncMock(return_value=None)

        # Mock transport message and device message
        transport_message = {"transportId": "test-transport-123"}
        device_message = {"device": "test-device", "status": "online"}

        # Create a proper async iterator for the websocket
        messages = [json.dumps(transport_message), json.dumps(device_message)]

        async def mock_recv():
            if not messages:
                raise ConnectionClosedOK(None, None)
            return messages.pop(0)

        mock_websocket.recv = mock_recv
        mock_websocket.__aiter__ = Mock(return_value=mock_websocket)

        async def mock_anext(self):
            try:
                return await self.recv()
            except ConnectionClosedOK as err:
                raise StopAsyncIteration from err

        mock_websocket.__anext__ = mock_anext

        callback = Mock()

        with patch(
            "micboard.manufacturers.shure.websocket.websockets.connect", return_value=mock_websocket
        ):
            with patch.object(self.client, "_make_request") as mock_request:
                mock_request.return_value = {"status": "success"}

                # The connection should close gracefully without raising an exception
                await connect_and_subscribe(self.client, "device1", callback)

                # Verify callback was called despite exception
                callback.assert_called_once_with(device_message)

    async def test_connect_and_subscribe_connection_closed_ok(self):
        """Test WebSocket connection closed gracefully."""
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__ = AsyncMock(return_value=mock_websocket)
        mock_websocket.__aexit__ = AsyncMock(return_value=None)

        # Mock transport message
        transport_message = {"transportId": "test-transport-123"}
        mock_websocket.recv = AsyncMock(return_value=json.dumps(transport_message))

        callback = Mock()

        with patch("micboard.shure.websocket.websockets.connect", return_value=mock_websocket):
            with patch.object(self.client, "_make_request") as mock_request:
                mock_request.return_value = {"status": "success"}

                # Simulate graceful connection close
                import websockets

                mock_websocket.recv.side_effect = websockets.exceptions.ConnectionClosedOK(
                    None, None
                )

                # This should complete without raising ShureWebSocketError
                await connect_and_subscribe(self.client, "device1", callback)

    async def test_connect_and_subscribe_connection_closed_error(self):
        """Test WebSocket connection closed with error."""
        mock_websocket = AsyncMock()
        mock_websocket.__aenter__ = AsyncMock(return_value=mock_websocket)
        mock_websocket.__aexit__ = AsyncMock(return_value=None)

        # Mock transport message
        transport_message = {"transportId": "test-transport-123"}
        mock_websocket.recv = AsyncMock(return_value=json.dumps(transport_message))

        callback = Mock()

        with patch("micboard.shure.websocket.websockets.connect", return_value=mock_websocket):
            with patch.object(self.client, "_make_request") as mock_request:
                mock_request.return_value = {"status": "success"}

                # Simulate connection error
                import websockets

                mock_websocket.recv.side_effect = websockets.exceptions.ConnectionClosedError(
                    None, None
                )

                with pytest.raises(
                    ShureWebSocketError, match="WebSocket connection error for device device1"
                ):
                    await connect_and_subscribe(self.client, "device1", callback)

    async def test_connect_and_subscribe_unhandled_exception(self):
        """Test WebSocket connection with unhandled exception."""
        callback = Mock()

        with patch(
            "micboard.shure.websocket.websockets.connect", side_effect=Exception("Network error")
        ):
            with pytest.raises(
                ShureWebSocketError, match="Unhandled WebSocket error for device device1"
            ):
                await connect_and_subscribe(self.client, "device1", callback)
