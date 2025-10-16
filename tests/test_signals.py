"""
Tests for Django signals.
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from micboard.models import Channel, DeviceAssignment, Manufacturer, Receiver, Transmitter
from micboard.signals import (
    assignment_saved,
    channel_saved,
    receiver_deleted,
    receiver_pre_delete,
    receiver_saved,
)


class ReceiverSignalsTest(TestCase):
    """Test receiver-related signals"""

    def setUp(self):
        self.manufacturer = Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
        )
        self.receiver = Receiver.objects.create(
            name="Test Receiver",
            api_device_id="TEST001",
            manufacturer=self.manufacturer,
            ip="192.168.1.100",
            device_type="ULXD4D",
            is_active=True,
        )

    def tearDown(self):
        # Clean up cache
        cache.clear()

    @patch("micboard.signals.logger")
    def test_receiver_created_signal(self, mock_logger):
        """Test signal when receiver is created"""
        # Create a new receiver to trigger the signal
        new_receiver = Receiver.objects.create(
            name="New Receiver",
            api_device_id="NEW001",
            manufacturer=self.manufacturer,
            ip="192.168.1.101",
            device_type="ULXD4D",
        )

        # Verify logging
        mock_logger.info.assert_called_with(
            "Receiver created: %s (%s) at %s",
            new_receiver.name,
            new_receiver.device_type,
            new_receiver.ip,
        )

        # Verify cache was cleared
        self.assertIsNone(cache.get("micboard_device_data"))

    @patch("micboard.signals.logger")
    def test_receiver_updated_signal_active(self, mock_logger):
        """Test signal when receiver is updated but stays active"""
        self.receiver.name = "Updated Receiver"
        self.receiver.save()

        # Should log debug message
        mock_logger.debug.assert_called_with("Receiver updated: %s", self.receiver.name)
        # Should not log info or broadcast offline status
        mock_logger.info.assert_not_called()

    @patch("micboard.signals.async_to_sync")
    @patch("micboard.signals.get_channel_layer")
    @patch("micboard.signals.logger")
    def test_receiver_updated_signal_offline(
        self, mock_logger, mock_get_channel_layer, mock_async_to_sync
    ):
        """Test signal when receiver goes offline"""
        # Mock channel layer
        mock_channel_layer = MagicMock()
        mock_get_channel_layer.return_value = mock_channel_layer
        mock_async_to_sync.return_value = MagicMock()

        # Make receiver inactive
        self.receiver.is_active = False
        self.receiver.save()

        # Verify logging
        mock_logger.debug.assert_called_with("Receiver updated: %s", self.receiver.name)

        # Verify WebSocket broadcast
        mock_async_to_sync.assert_called_once()
        mock_async_to_sync.return_value.assert_called_once_with(
            mock_channel_layer.group_send(
                "micboard_updates",
                {
                    "type": "receiver_status",
                    "receiver_id": self.receiver.api_device_id,
                    "is_active": False,
                },
            )
        )

    @patch("micboard.signals.logger")
    def test_receiver_signal_error_handling(self, mock_logger):
        """Test error handling in receiver signal"""
        # Create a receiver that will cause an error
        with patch.object(
            self.receiver,
            "name",
            new_callable=lambda: (_ for _ in ()).throw(Exception("Test error")),
        ):
            # This should trigger the exception handler
            receiver_saved(Receiver, self.receiver, created=True)

        mock_logger.exception.assert_called_with("Error in receiver_saved signal handler")

    @patch("micboard.signals.logger")
    def test_receiver_pre_delete_signal(self, mock_logger):
        """Test pre-delete signal for receivers"""
        # Set up some cache entries
        cache.set(f"receiver_{self.receiver.api_device_id}", "test_data")
        cache.set(f"channels_{self.receiver.api_device_id}", "channel_data")
        cache.set("micboard_device_data", "device_data")

        # Trigger pre-delete
        receiver_pre_delete(Receiver, self.receiver)

        # Verify cache cleanup
        self.assertIsNone(cache.get(f"receiver_{self.receiver.api_device_id}"))
        self.assertIsNone(cache.get(f"channels_{self.receiver.api_device_id}"))
        self.assertIsNone(cache.get("micboard_device_data"))

        # Verify logging
        mock_logger.info.assert_called_with("Cleaned up cache for receiver: %s", self.receiver.name)

    @patch("micboard.signals.logger")
    def test_receiver_pre_delete_error_handling(self, mock_logger):
        """Test error handling in pre-delete signal"""
        with patch("micboard.signals.cache.delete_many", side_effect=Exception("Cache error")):
            receiver_pre_delete(Receiver, self.receiver)

        mock_logger.exception.assert_called_with("Error cleaning up receiver cache")

    @patch("micboard.signals.async_to_sync")
    @patch("micboard.signals.get_channel_layer")
    @patch("micboard.signals.logger")
    def test_receiver_deleted_signal(self, mock_logger, mock_get_channel_layer, mock_async_to_sync):
        """Test post-delete signal for receivers"""
        # Mock channel layer
        mock_channel_layer = MagicMock()
        mock_get_channel_layer.return_value = mock_channel_layer
        mock_async_to_sync.return_value = MagicMock()

        # Trigger delete signal
        receiver_deleted(Receiver, self.receiver)

        # Verify logging
        mock_logger.info.assert_called_with(
            "Receiver deleted: %s (%s)", self.receiver.name, self.receiver.api_device_id
        )

        # Verify WebSocket broadcast
        mock_async_to_sync.assert_called_once()
        mock_async_to_sync.return_value.assert_called_once_with(
            mock_channel_layer.group_send(
                "micboard_updates",
                {
                    "type": "receiver_deleted",
                    "receiver_id": self.receiver.api_device_id,
                },
            )
        )

    @patch("micboard.signals.logger")
    def test_receiver_deleted_error_handling(self, mock_logger):
        """Test error handling in delete signal"""
        with patch("micboard.signals.get_channel_layer", side_effect=Exception("Channel error")):
            receiver_deleted(Receiver, self.receiver)

        mock_logger.exception.assert_called_with("Error in receiver_deleted signal handler")


class ChannelSignalsTest(TestCase):
    """Test channel-related signals"""

    def setUp(self):
        self.manufacturer = Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
        )
        self.receiver = Receiver.objects.create(
            name="Test Receiver",
            api_device_id="TEST001",
            manufacturer=self.manufacturer,
            ip="192.168.1.100",
            device_type="ULXD4D",
        )
        self.channel = Channel.objects.create(
            receiver=self.receiver,
            channel_number=1,
            frequency=584.000,
        )

    @patch("micboard.signals.logger")
    def test_channel_created_signal(self, mock_logger):
        """Test signal when channel is created"""
        # Create a new channel to trigger the signal
        new_channel = Channel.objects.create(
            receiver=self.receiver,
            channel_number=2,
            frequency=585.000,
        )

        # Verify logging
        mock_logger.debug.assert_called_with(
            "Channel created: %s channel %d",
            new_channel.receiver.name,
            new_channel.channel_number,
        )

    @patch("micboard.signals.logger")
    def test_channel_signal_error_handling(self, mock_logger):
        """Test error handling in channel signal"""
        with patch.object(
            self.channel,
            "receiver",
            new_callable=lambda: (_ for _ in ()).throw(Exception("Test error")),
        ):
            channel_saved(Channel, self.channel, created=True)

        mock_logger.exception.assert_called_with("Error in channel_saved signal handler")


class TransmitterSignalsTest(TestCase):
    """Test transmitter-related signals"""

    def setUp(self):
        self.manufacturer = Manufacturer.objects.create(
            code="shure",
            name="Shure Incorporated",
        )
        self.receiver = Receiver.objects.create(
            api_device_id="test-device-001",
            manufacturer=self.manufacturer,
            ip="192.168.1.100",
            device_type="uhfr",
            name="Test Receiver",
        )
        self.channel = Channel.objects.create(
            receiver=self.receiver,
            channel_number=1,
        )
        self.transmitter = Transmitter.objects.create(
            channel=self.channel,
            slot=1,
            frequency="584.000",
        )

    @patch("micboard.signals.logger")
    def test_transmitter_created_signal(self, mock_logger):
        """Test signal when transmitter is created"""
        # Create a new transmitter to trigger the signal
        channel2 = Channel.objects.create(
            receiver=self.receiver,
            channel_number=2,
        )
        new_transmitter = Transmitter.objects.create(
            channel=channel2,
            slot=2,
            frequency="585.000",
        )

        # Verify logging
        mock_logger.debug.assert_called_with(
            "Transmitter created for slot %d", new_transmitter.slot
        )

    # @patch("micboard.signals.logger")
    # def test_transmitter_signal_error_handling(self, mock_logger):
    #     """Test error handling in transmitter signal"""
    #     from unittest.mock import PropertyMock, Mock

    #     with patch.object(
    #         self.transmitter,
    #         "slot",
    #         new_callable=PropertyMock,
    #     ) as mock_slot:
    #         mock_slot.__get__ = Mock(side_effect=Exception("Test error"))
    #         transmitter_saved(Transmitter, self.transmitter, created=True)

    #     mock_logger.exception.assert_called_with("Error in transmitter_saved signal handler")


class DeviceAssignmentSignalsTest(TestCase):
    """Test device assignment signals"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.manufacturer = Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
        )
        self.receiver = Receiver.objects.create(
            name="Test Receiver",
            api_device_id="TEST001",
            manufacturer=self.manufacturer,
            ip="192.168.1.100",
            device_type="ULXD4D",
        )
        self.channel = Channel.objects.create(
            receiver=self.receiver,
            channel_number=1,
            frequency=584.000,
        )
        self.assignment = DeviceAssignment.objects.create(
            user=self.user,
            channel=self.channel,
            priority=1,
        )

    @patch("micboard.signals.logger")
    def test_assignment_created_signal(self, mock_logger):
        """Test signal when assignment is created"""
        # Create a new assignment to trigger the signal
        new_assignment = DeviceAssignment.objects.create(
            user=self.user,
            channel=self.channel,
            priority=2,
        )

        # Verify logging
        mock_logger.info.assert_called_with(
            "Assignment created: %s -> %s (priority: %s)",
            new_assignment.user.username,
            new_assignment.channel,
            new_assignment.priority,
        )

    @patch("micboard.signals.logger")
    def test_assignment_updated_signal(self, mock_logger):
        """Test signal when assignment is updated"""
        self.assignment.priority = 3
        self.assignment.save()

        # Verify logging
        mock_logger.debug.assert_called_with(
            "Assignment updated: %s -> %s", self.assignment.user.username, self.assignment.channel
        )

    @patch("micboard.signals.logger")
    def test_assignment_signal_error_handling(self, mock_logger):
        """Test error handling in assignment signal"""
        with patch.object(
            self.assignment,
            "user",
            new_callable=lambda: (_ for _ in ()).throw(Exception("Test error")),
        ):
            assignment_saved(DeviceAssignment, self.assignment, created=True)

        mock_logger.exception.assert_called_with("Error in assignment_saved signal handler")


class SignalIntegrationTest(TestCase):
    """Integration tests for signal interactions"""

    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.manufacturer = Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
        )
        self.receiver = Receiver.objects.create(
            name="Test Receiver",
            api_device_id="TEST001",
            manufacturer=self.manufacturer,
            ip="192.168.1.100",
            device_type="ULXD4D",
        )

    def tearDown(self):
        cache.clear()

    @patch("micboard.signals.async_to_sync")
    @patch("micboard.signals.get_channel_layer")
    @patch("micboard.signals.logger")
    def test_full_receiver_lifecycle(self, mock_logger, mock_get_channel_layer, mock_async_to_sync):
        """Test complete receiver lifecycle with all signals"""
        # Mock channel layer
        mock_channel_layer = MagicMock()
        mock_get_channel_layer.return_value = mock_channel_layer
        mock_async_to_sync.return_value = MagicMock()

        # 1. Create receiver
        receiver = Receiver.objects.create(
            name="Lifecycle Receiver",
            api_device_id="LIFE001",
            manufacturer=self.manufacturer,
            ip="192.168.1.200",
            device_type="ULXD4D",
        )

        # 2. Update receiver (make offline)
        receiver.is_active = False
        receiver.save()

        # 3. Delete receiver
        receiver_id = receiver.api_device_id
        receiver_name = receiver.name
        receiver.delete()

        # Verify all logging calls were made
        mock_logger.info.assert_any_call(
            "Receiver created: %s (%s) at %s",
            receiver_name,
            "ULXD4D",
            "192.168.1.200",
        )
        mock_logger.debug.assert_any_call("Receiver updated: %s", receiver_name)
        mock_logger.info.assert_any_call("Cleaned up cache for receiver: %s", receiver_name)
        mock_logger.info.assert_any_call("Receiver deleted: %s (%s)", receiver_name, receiver_id)

        # Verify WebSocket broadcasts
        self.assertEqual(mock_async_to_sync.call_count, 2)  # One for offline, one for deletion
