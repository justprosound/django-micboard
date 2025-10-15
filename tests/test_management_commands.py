"""
Tests for Django management commands: check_api_health and poll_devices.
"""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase


class TestCheckApiHealthCommand(TestCase):
    @patch("micboard.shure.client.ShureSystemAPIClient")
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

    @patch("micboard.shure.client.ShureSystemAPIClient")
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
        self.assertIn("API Health: unhealthy", out.getvalue())


class TestPollDevicesCommand(TestCase):
    @patch("micboard.shure.client.ShureSystemAPIClient")
    @patch("micboard.serializers.serialize_receivers")
    @patch("channels.layers.get_channel_layer")
    def test_poll_devices_initial_poll_only(self, mock_channel_layer, mock_serialize, mock_client):
        mock_instance = mock_client.return_value
        mock_instance.poll_all_devices.return_value = {"dev1": {"name": "Device 1"}}
        mock_serialize.return_value = [{"name": "Device 1"}]
        out = StringIO()
        call_command("poll_devices", initial_poll_only=True, stdout=out)
        self.assertIn("Initial poll complete", out.getvalue())

    @patch("micboard.shure.client.ShureSystemAPIClient")
    @patch("micboard.serializers.serialize_receivers")
    @patch("channels.layers.get_channel_layer")
    def test_poll_devices_no_broadcast(self, mock_channel_layer, mock_serialize, mock_client):
        mock_instance = mock_client.return_value
        mock_instance.poll_all_devices.return_value = {"dev2": {"name": "Device 2"}}
        mock_serialize.return_value = [{"name": "Device 2"}]
        out = StringIO()
        call_command("poll_devices", no_broadcast=True, stdout=out)
        self.assertIn("Broadcasting disabled", out.getvalue())
