"""
Tests for WebSocket consumers.
"""

import json
from unittest.mock import AsyncMock, patch

from django.test import TestCase

from micboard.consumers import MicboardConsumer


class MicboardConsumerTest(TestCase):
    """Test WebSocket consumer for real-time updates"""

    def setUp(self):
        self.consumer = MicboardConsumer()

    async def test_connect(self):
        """Test WebSocket connection"""
        # Mock the channel layer and scope
        mock_scope = {
            "type": "websocket",
            "path": "/ws/micboard/",
            "headers": [],
        }

        consumer = MicboardConsumer()
        consumer.scope = mock_scope
        consumer.channel_name = "test_channel"
        consumer.channel_layer = AsyncMock()

        # Mock group_add and accept
        consumer.channel_layer.group_add = AsyncMock()
        consumer.accept = AsyncMock()

        with patch("micboard.consumers.logger") as mock_logger:
            await consumer.connect()

            # Verify group join
            consumer.channel_layer.group_add.assert_called_once_with(
                "micboard_updates", "test_channel"
            )

            # Verify connection acceptance
            consumer.accept.assert_called_once()

            # Verify logging
            mock_logger.info.assert_called_once_with("WebSocket connected: test_channel")

    async def test_disconnect(self):
        """Test WebSocket disconnection"""
        mock_scope = {"type": "websocket"}
        consumer = MicboardConsumer()
        consumer.scope = mock_scope
        consumer.channel_name = "test_channel"
        consumer.channel_layer = AsyncMock()
        consumer.room_group_name = "micboard_updates"

        # Mock group_discard
        consumer.channel_layer.group_discard = AsyncMock()

        with patch("micboard.consumers.logger") as mock_logger:
            await consumer.disconnect(1000)

            # Verify group leave
            consumer.channel_layer.group_discard.assert_called_once_with(
                "micboard_updates", "test_channel"
            )

            # Verify logging
            mock_logger.info.assert_called_once_with("WebSocket disconnected: test_channel")

    async def test_receive_ping_command(self):
        """Test receiving ping command from client"""
        mock_scope = {"type": "websocket"}
        consumer = MicboardConsumer()
        consumer.scope = mock_scope
        consumer.send = AsyncMock()

        # Send ping command
        ping_data = {"command": "ping"}
        await consumer.receive(text_data=json.dumps(ping_data))

        # Verify pong response
        consumer.send.assert_called_once_with(text_data=json.dumps({"type": "pong"}))

    async def test_receive_invalid_json(self):
        """Test receiving invalid JSON"""
        mock_scope = {"type": "websocket"}
        consumer = MicboardConsumer()
        consumer.scope = mock_scope

        with patch("micboard.consumers.logger") as mock_logger:
            await consumer.receive(text_data="invalid json")

            # Verify error logging
            mock_logger.exception.assert_called_once()
            call_args = mock_logger.exception.call_args[0]
            self.assertIn("Invalid JSON received", call_args[0])
            self.assertIn("invalid json", call_args[1])

    async def test_receive_no_command(self):
        """Test receiving message without command"""
        mock_scope = {"type": "websocket"}
        consumer = MicboardConsumer()
        consumer.scope = mock_scope
        consumer.send = AsyncMock()

        # Send message without command
        data = {"some": "data"}
        await consumer.receive(text_data=json.dumps(data))

        # Should not send any response
        consumer.send.assert_not_called()

    async def test_receive_unknown_command(self):
        """Test receiving unknown command"""
        mock_scope = {"type": "websocket"}
        consumer = MicboardConsumer()
        consumer.scope = mock_scope
        consumer.send = AsyncMock()

        # Send unknown command
        data = {"command": "unknown"}
        await consumer.receive(text_data=json.dumps(data))

        # Should not send any response
        consumer.send.assert_not_called()

    async def test_receive_bytes_data(self):
        """Test receiving bytes data (should be ignored)"""
        mock_scope = {"type": "websocket"}
        consumer = MicboardConsumer()
        consumer.scope = mock_scope
        consumer.send = AsyncMock()

        await consumer.receive(text_data=None, bytes_data=b"some bytes")

        # Should not send any response
        consumer.send.assert_not_called()

    async def test_device_update_broadcast(self):
        """Test broadcasting device updates"""
        mock_scope = {"type": "websocket"}
        consumer = MicboardConsumer()
        consumer.scope = mock_scope
        consumer.send = AsyncMock()

        # Simulate device update event
        event = {
            "type": "device_update",
            "data": {
                "receivers": [{"id": 1, "name": "Receiver 1"}],
                "transmitters": [{"id": 1, "name": "Transmitter 1"}],
            },
        }

        await consumer.device_update(event)

        # Verify message sent to client
        expected_message = {"type": "device_update", "data": event["data"]}
        consumer.send.assert_called_once_with(text_data=json.dumps(expected_message))

    async def test_status_update_broadcast(self):
        """Test broadcasting status updates"""
        mock_scope = {"type": "websocket"}
        consumer = MicboardConsumer()
        consumer.scope = mock_scope
        consumer.send = AsyncMock()

        # Simulate status update event
        event = {"type": "status_update", "message": "System is running normally"}

        await consumer.status_update(event)

        # Verify message sent to client
        expected_message = {"type": "status", "message": "System is running normally"}
        consumer.send.assert_called_once_with(text_data=json.dumps(expected_message))

    async def test_room_group_name_assignment(self):
        """Test that room group name is correctly assigned"""
        consumer = MicboardConsumer()
        self.assertEqual(consumer.room_group_name, "micboard_updates")

    @patch("channels.generic.websocket.AsyncWebsocketConsumer.__init__")
    async def test_inheritance(self, mock_init):
        """Test that consumer inherits from AsyncWebsocketConsumer"""
        mock_init.return_value = None
        MicboardConsumer()
        mock_init.assert_called_once()


class MicboardConsumerIntegrationTest(TestCase):
    """Integration tests for WebSocket consumer"""

    async def test_websocket_communicator_flow(self):
        """Test full WebSocket flow with communicator"""
        # This would require setting up Django Channels routing
        # For now, we'll test the individual methods
        consumer = MicboardConsumer()

        # Test that consumer has required methods
        self.assertTrue(hasattr(consumer, "connect"))
        self.assertTrue(hasattr(consumer, "disconnect"))
        self.assertTrue(hasattr(consumer, "receive"))
        self.assertTrue(hasattr(consumer, "device_update"))
        self.assertTrue(hasattr(consumer, "status_update"))

    async def test_event_handling_types(self):
        """Test that event handlers accept correct types"""
        consumer = MicboardConsumer()
        consumer.send = AsyncMock()

        # Test device_update with various data types
        events = [
            {"type": "device_update", "data": {"key": "value"}},
            {"type": "device_update", "data": [1, 2, 3]},
            {"type": "device_update", "data": None},
        ]

        for event in events:
            consumer.send.reset_mock()
            await consumer.device_update(event)
            consumer.send.assert_called_once()

        # Test status_update with various messages
        status_events = [
            {"type": "status_update", "message": "OK"},
            {"type": "status_update", "message": ""},
            {"type": "status_update", "message": None},
        ]

        for event in status_events:
            consumer.send.reset_mock()
            await consumer.status_update(event)
            consumer.send.assert_called_once()
