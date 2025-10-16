"""
Tests for Django management commands: check_api_health and poll_devices.
"""

from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase

from micboard.models import Manufacturer


class TestCheckApiHealthCommand(TestCase):
    @patch("micboard.management.commands.check_api_health.ShureSystemAPIClient")
    def test_check_api_health_json_output(self, mock_client):
        mock_instance = mock_client.return_value
        mock_instance.check_health.return_value = {
            "status": "healthy",
            "base_url": "http://localhost:8080",
            "status_code": 200,
            "consecutive_failures": 0,
            "last_successful_request": 1234567890,
        }
        out = StringIO()
        call_command("check_api_health", json=True, stdout=out)
        self.assertIn('"status": "healthy"', out.getvalue())

    @patch("micboard.management.commands.check_api_health.ShureSystemAPIClient")
    def test_check_api_health_text_output(self, mock_client):
        mock_instance = mock_client.return_value
        mock_instance.check_health.return_value = {
            "status": "unhealthy",
            "base_url": "http://localhost:8080",
            "status_code": 500,
            "consecutive_failures": 2,
            "last_successful_request": None,
        }
        out = StringIO()
        call_command("check_api_health", stdout=out)
        self.assertIn("API is unhealthy", out.getvalue())


class TestPollDevicesCommand(TestCase):
    @patch("micboard.management.commands.poll_devices.get_manufacturer_plugin")
    @patch("micboard.serializers.serialize_receivers")
    @patch("channels.layers.get_channel_layer")
    def test_poll_devices_initial_poll_only(
        self, mock_channel_layer, mock_serialize, mock_get_plugin
    ):
        """Test poll_devices with initial poll only"""
        # Create a manufacturer for the test
        Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
        )

        # Mock plugin
        mock_plugin_class = Mock()
        mock_plugin = Mock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin.get_devices.return_value = {
            "dev1": {"name": "Device 1", "ip": "192.168.1.100", "type": "uhfr", "channels": []}
        }
        mock_get_plugin.return_value = mock_plugin_class
        mock_serialize.return_value = [{"name": "Device 1"}]

        # Mock the channel_layer.group_send as an async function
        async def mock_group_send(*args, **kwargs):
            pass

        mock_channel_layer.return_value.group_send = mock_group_send

        out = StringIO()
        call_command("poll_devices", initial_poll_only=True, stdout=out)
        self.assertIn("Initial poll complete", out.getvalue())

    @patch("micboard.management.commands.poll_devices.get_manufacturer_plugin")
    @patch("micboard.serializers.serialize_receivers")
    @patch("channels.layers.get_channel_layer")
    def test_poll_devices_no_broadcast(self, mock_channel_layer, mock_serialize, mock_get_plugin):
        """Test poll_devices with no broadcast"""
        # Create a manufacturer for the test
        Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
        )

        # Mock plugin
        mock_plugin_class = Mock()
        mock_plugin = Mock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin.get_devices.return_value = {
            "dev2": {"name": "Device 2", "ip": "192.168.1.101", "type": "uhfr", "channels": []}
        }
        mock_get_plugin.return_value = mock_plugin_class
        mock_serialize.return_value = [{"name": "Device 2"}]

        out = StringIO()
        call_command("poll_devices", no_broadcast=True, initial_poll_only=True, stdout=out)
        self.assertIn("Broadcasting disabled", out.getvalue())

    @patch("micboard.management.commands.poll_devices.get_manufacturer_plugin")
    @patch("micboard.serializers.serialize_receivers")
    @patch("channels.layers.get_channel_layer")
    def test_poll_devices_manufacturer_filtering(
        self, mock_channel_layer, mock_serialize, mock_get_plugin
    ):
        """Test poll_devices with manufacturer filtering"""
        # Create test manufacturer
        manufacturer = Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
        )

        # Mock plugin
        mock_plugin_class = Mock()
        mock_plugin = Mock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin.get_devices.return_value = {
            "dev1": {"name": "Device 1", "ip": "192.168.1.100", "type": "uhfr", "channels": []}
        }
        mock_get_plugin.return_value = mock_plugin_class
        mock_serialize.return_value = [{"name": "Device 1"}]

        # Mock the channel_layer.group_send as an async function
        async def mock_group_send(*args, **kwargs):
            pass

        mock_channel_layer.return_value.group_send = mock_group_send

        out = StringIO()
        call_command("poll_devices", manufacturer="shure", initial_poll_only=True, stdout=out)
        self.assertIn("Initial poll complete", out.getvalue())

        # Verify the plugin was created with the manufacturer
        mock_plugin_class.assert_called_once_with(manufacturer)
