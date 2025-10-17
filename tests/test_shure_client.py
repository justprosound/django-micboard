"""
Tests for Shure System API client.
"""

import json
import time
from functools import wraps
from unittest.mock import Mock, patch

import requests
from django.test import TestCase, override_settings

from micboard.manufacturers.shure.client import (
    ShureAPIError,
    ShureAPIRateLimitError,
    ShureSystemAPIClient,
)


def rate_limit(calls_per_second):
    min_interval = 1.0 / calls_per_second
    last_call_time = 0.0

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal last_call_time
            now = time.time()
            elapsed = now - last_call_time

            if elapsed < min_interval:
                sleep_time = min_interval - elapsed
                time.sleep(sleep_time)

            last_call_time = time.time()
            return func(*args, **kwargs)

        return wrapper

    return decorator


class ShureAPIErrorTest(TestCase):
    """Test Shure API error classes"""

    def test_shure_api_error_basic(self):
        """Test basic ShureAPIError"""
        error = ShureAPIError("Test error")
        self.assertEqual(str(error), "ShureAPIError: Test error")
        self.assertEqual(error.message, "Test error")
        self.assertIsNone(error.status_code)
        self.assertIsNone(error.response)

    def test_shure_api_error_with_status(self):
        """Test ShureAPIError with status code"""
        error = ShureAPIError("Test error", status_code=404)
        self.assertEqual(str(error), "ShureAPIError: Test error (Status: 404)")
        self.assertEqual(error.status_code, 404)

    def test_shure_api_error_with_response(self):
        """Test ShureAPIError with response"""
        mock_response = Mock()
        error = ShureAPIError("Test error", status_code=500, response=mock_response)
        self.assertEqual(error.response, mock_response)

    def test_shure_api_rate_limit_error_basic(self):
        """Test basic ShureAPIRateLimitError"""
        error = ShureAPIRateLimitError()
        self.assertEqual(str(error), "ShureAPIRateLimitError: Rate limit exceeded")
        self.assertEqual(error.status_code, 429)
        self.assertIsNone(error.retry_after)

    def test_shure_api_rate_limit_error_with_retry_after(self):
        """Test ShureAPIRateLimitError with retry_after"""
        error = ShureAPIRateLimitError(retry_after=30)
        self.assertEqual(
            str(error), "ShureAPIRateLimitError: Rate limit exceeded. Retry after 30 seconds."
        )
        self.assertEqual(error.retry_after, 30)

    def test_shure_api_rate_limit_error_from_response(self):
        """Test ShureAPIRateLimitError extracts retry_after from response"""
        mock_response = Mock()
        mock_response.headers = {"Retry-After": "60"}
        error = ShureAPIRateLimitError(response=mock_response)
        self.assertEqual(error.retry_after, 60)

    def test_shure_api_rate_limit_error_invalid_retry_after(self):
        """Test ShureAPIRateLimitError handles invalid retry_after header"""
        mock_response = Mock()
        mock_response.headers = {"Retry-After": "invalid"}
        error = ShureAPIRateLimitError(response=mock_response)
        self.assertIsNone(error.retry_after)


class RateLimitDecoratorTest(TestCase):
    """Test rate limiting decorator"""

    def setUp(self):
        # Clear cache before each test
        from django.core.cache import cache

        cache.clear()

    @patch("time.sleep")
    @patch("time.time")
    def test_rate_limit_basic(self, mock_time, mock_sleep):
        """Test basic rate limiting"""
        mock_time.return_value = 1000.0

        @rate_limit(calls_per_second=2.0)  # 0.5 second intervals
        def test_func(self):
            return "called"

        # First call
        result = test_func(self)
        self.assertEqual(result, "called")

        # Second call immediately after - should sleep
        mock_time.return_value = 1000.1  # 0.1 seconds later
        result = test_func(self)
        self.assertEqual(result, "called")
        # Floating point math can introduce tiny rounding differences; assert close
        mock_sleep.assert_called_once()
        called_arg = mock_sleep.call_args[0][0]
        self.assertAlmostEqual(called_arg, 0.4, places=6)

    @patch("time.time")
    def test_rate_limit_no_delay_needed(self, mock_time):
        """Test rate limiting when no delay is needed"""
        mock_time.return_value = 1000.0

        @rate_limit(calls_per_second=1.0)
        def test_func(self):
            return "called"

        # First call
        test_func(self)

        # Second call after sufficient time
        mock_time.return_value = 1001.1  # More than 1 second later
        with patch("time.sleep") as mock_sleep:
            test_func(self)
            mock_sleep.assert_not_called()


class ShureSystemAPIClientTest(TestCase):
    """Test ShureSystemAPIClient"""

    def setUp(self):
        self.client = ShureSystemAPIClient()

    @override_settings(
        MICBOARD_CONFIG={
            "SHURE_API_BASE_URL": "http://test.example.com",
            "SHURE_API_USERNAME": "testuser",
            "SHURE_API_PASSWORD": "testpass",
            "SHURE_API_TIMEOUT": 30,
            "SHURE_API_VERIFY_SSL": False,
            "SHURE_API_MAX_RETRIES": 5,
            "SHURE_API_RETRY_BACKOFF": 1.0,
        }
    )
    def test_client_initialization_with_config(self):
        """Test client initialization with Django settings"""
        client = ShureSystemAPIClient()

        self.assertEqual(client.base_url, "http://test.example.com")
        self.assertEqual(client.username, "testuser")
        self.assertEqual(client.password, "testpass")
        self.assertEqual(client.timeout, 30)
        self.assertFalse(client.verify_ssl)
        self.assertEqual(client.max_retries, 5)
        self.assertEqual(client.retry_backoff, 1.0)

    def test_client_initialization_defaults(self):
        """Test client initialization with defaults"""
        client = ShureSystemAPIClient()

        self.assertEqual(client.base_url, "http://localhost:8080")
        self.assertIsNone(client.username)
        self.assertIsNone(client.password)
        self.assertEqual(client.timeout, 10)
        self.assertTrue(client.verify_ssl)
        self.assertEqual(client.max_retries, 3)
        self.assertEqual(client.retry_backoff, 0.5)

    def test_websocket_url_inference(self):
        """Test WebSocket URL inference from base URL"""
        client = ShureSystemAPIClient()
        client.base_url = "https://api.example.com"

        # Should infer wss:// from https://
        expected_ws_url = "wss://api.example.com/api/v1/subscriptions/websocket/create"
        self.assertEqual(client.websocket_url, expected_ws_url)

        # Test http to ws conversion
        client.base_url = "http://api.example.com"
        expected_ws_url = "ws://api.example.com/api/v1/subscriptions/websocket/create"
        self.assertEqual(client.websocket_url, expected_ws_url)

    @override_settings(MICBOARD_CONFIG={"SHURE_API_WEBSOCKET_URL": "ws://custom.websocket.url"})
    def test_websocket_url_explicit_config(self):
        """Test explicit WebSocket URL configuration"""
        client = ShureSystemAPIClient()
        self.assertEqual(client.websocket_url, "ws://custom.websocket.url")

    def test_is_healthy_initial_state(self):
        """Test initial healthy state"""
        client = ShureSystemAPIClient()
        self.assertTrue(client.is_healthy())
        self.assertTrue(client._is_healthy)
        self.assertEqual(client._consecutive_failures, 0)

    def test_is_healthy_after_failures(self):
        """Test healthy state after consecutive failures"""
        client = ShureSystemAPIClient()
        client._consecutive_failures = 5
        self.assertFalse(client.is_healthy())

        client._consecutive_failures = 3
        client._is_healthy = False
        self.assertFalse(client.is_healthy())

    @patch("requests.Session.get")
    def test_check_health_success(self, mock_get):
        """Test successful health check"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        client = ShureSystemAPIClient()
        result = client.check_health()

        expected = {
            "status": "healthy",
            "base_url": "http://localhost:8080",
            "status_code": 200,
            "consecutive_failures": 0,
            "last_successful_request": None,
        }
        self.assertEqual(result, expected)

    @patch("requests.Session.get")
    def test_check_health_unhealthy(self, mock_get):
        """Test unhealthy health check"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        client = ShureSystemAPIClient()
        result = client.check_health()

        self.assertEqual(result["status"], "unhealthy")
        self.assertEqual(result["status_code"], 500)

    @patch("requests.Session.get")
    def test_check_health_connection_error(self, mock_get):
        """Test health check with connection error"""
        mock_get.side_effect = requests.ConnectionError("Connection failed")

        client = ShureSystemAPIClient()
        result = client.check_health()

        self.assertEqual(result["status"], "unreachable")
        self.assertIn("Connection failed", result["error"])

    @patch("requests.Session.request")
    def test_make_request_success(self, mock_request):
        """Test successful request"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'{"test": "data"}'
        mock_response.json.return_value = {"test": "data"}
        mock_request.return_value = mock_response

        client = ShureSystemAPIClient()
        result = client._make_request("GET", "/test")

        self.assertEqual(result, {"test": "data"})
        self.assertTrue(client._is_healthy)
        self.assertEqual(client._consecutive_failures, 0)
        self.assertIsNotNone(client._last_successful_request)

    @patch("requests.Session.request")
    def test_make_request_http_error_429(self, mock_request):
        """Test request with rate limit error"""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "30"}
        mock_request.return_value = mock_response

        client = ShureSystemAPIClient()

        with self.assertRaises(ShureAPIRateLimitError) as cm:
            client._make_request("GET", "/test")

        self.assertEqual(cm.exception.status_code, 429)
        self.assertEqual(cm.exception.retry_after, 30)
        self.assertEqual(client._consecutive_failures, 1)

    @patch("requests.Session.request")
    def test_make_request_http_error_other(self, mock_request):
        """Test request with other HTTP error"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        mock_request.return_value = mock_response

        client = ShureSystemAPIClient()

        with self.assertRaises(ShureAPIError) as cm:
            client._make_request("GET", "/test")

        self.assertEqual(cm.exception.status_code, 404)
        self.assertEqual(client._consecutive_failures, 1)

    @patch("requests.Session.request")
    def test_make_request_connection_error(self, mock_request):
        """Test request with connection error"""
        mock_request.side_effect = requests.ConnectionError("Connection failed")

        client = ShureSystemAPIClient()

        with self.assertRaises(ShureAPIError) as cm:
            client._make_request("GET", "/test")

        self.assertIn("Connection error", str(cm.exception))
        self.assertEqual(client._consecutive_failures, 1)
        self.assertFalse(client._is_healthy)

    @patch("requests.Session.request")
    def test_make_request_timeout_error(self, mock_request):
        """Test request with timeout error"""
        mock_request.side_effect = requests.Timeout("Timeout")

        client = ShureSystemAPIClient()

        with self.assertRaises(ShureAPIError) as cm:
            client._make_request("GET", "/test")

        self.assertIn("Timeout error", str(cm.exception))
        self.assertEqual(client._consecutive_failures, 1)

    @patch("requests.Session.request")
    def test_make_request_json_decode_error(self, mock_request):
        """Test request with invalid JSON response"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b"invalid json"
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "invalid json", 0)
        mock_request.return_value = mock_response

        client = ShureSystemAPIClient()

        with self.assertRaises(ShureAPIError) as cm:
            client._make_request("GET", "/test")

        self.assertIn("Invalid JSON response", str(cm.exception))
        self.assertEqual(client._consecutive_failures, 1)

    @patch("micboard.manufacturers.shure.client.ShureSystemAPIClient._make_request")
    def test_get_devices_success(self, mock_make_request):
        """Test successful get_devices"""
        mock_make_request.return_value = [{"id": "device1"}, {"id": "device2"}]

        client = ShureSystemAPIClient()
        result = client.get_devices()

        self.assertEqual(result, [{"id": "device1"}, {"id": "device2"}])
        mock_make_request.assert_called_once_with("GET", "/api/v1/devices")

    @patch("micboard.manufacturers.shure.client.ShureSystemAPIClient._make_request")
    def test_get_devices_invalid_response(self, mock_make_request):
        """Test get_devices with invalid response"""
        mock_make_request.return_value = "invalid"

        client = ShureSystemAPIClient()
        result = client.get_devices()

        self.assertEqual(result, [])

    @patch("micboard.manufacturers.shure.client.ShureSystemAPIClient._make_request")
    def test_get_device_success(self, mock_make_request):
        """Test successful get_device"""
        mock_make_request.return_value = {"id": "device1", "name": "Test Device"}

        client = ShureSystemAPIClient()
        result = client.get_device("device1")

        self.assertEqual(result, {"id": "device1", "name": "Test Device"})
        mock_make_request.assert_called_once_with("GET", "/api/v1/devices/device1")

    @patch("micboard.manufacturers.shure.client.ShureSystemAPIClient._make_request")
    def test_get_device_channels_success(self, mock_make_request):
        """Test successful get_device_channels"""
        mock_make_request.return_value = [{"channel": 1}, {"channel": 2}]

        client = ShureSystemAPIClient()
        result = client.get_device_channels("device1")

        self.assertEqual(result, [{"channel": 1}, {"channel": 2}])
        mock_make_request.assert_called_once_with("GET", "/api/v1/devices/device1/channels")

    @patch("micboard.manufacturers.shure.client.ShureSystemAPIClient._make_request")
    def test_get_transmitter_data_success(self, mock_make_request):
        """Test successful get_transmitter_data"""
        mock_make_request.return_value = {"battery": 80, "rf_level": -50}

        client = ShureSystemAPIClient()
        result = client.get_transmitter_data("device1", 1)

        self.assertEqual(result, {"battery": 80, "rf_level": -50})
        mock_make_request.assert_called_once_with("GET", "/api/v1/devices/device1/channels/1/tx")

    @patch("micboard.manufacturers.shure.client.ShureSystemAPIClient._make_request")
    def test_get_device_identity_success(self, mock_make_request):
        """Test successful get_device_identity"""
        mock_make_request.return_value = {"serialNumber": "ABC123"}

        client = ShureSystemAPIClient()
        result = client.get_device_identity("device1")

        self.assertEqual(result, {"serialNumber": "ABC123"})

    @patch("micboard.manufacturers.shure.client.ShureSystemAPIClient._make_request")
    def test_get_device_identity_not_available(self, mock_make_request):
        """Test get_device_identity when endpoint not available"""
        mock_make_request.side_effect = ShureAPIError("Not found")

        client = ShureSystemAPIClient()
        result = client.get_device_identity("device1")

        self.assertIsNone(result)

    @patch("micboard.manufacturers.shure.client.ShureSystemAPIClient._make_request")
    def test_enrich_device_data(self, mock_make_request):
        """Test device data enrichment"""
        client = ShureSystemAPIClient()

        # Mock the enrichment endpoints
        def mock_make_request_side_effect(method, endpoint, **kwargs):
            if "identify" in endpoint:
                return {"serialNumber": "ABC123", "firmwareVersion": "2.0.0"}
            elif "network" in endpoint:
                return {"hostname": "device1.local", "macAddress": "00:11:22:33:44:55"}
            elif "status" in endpoint:
                return {"frequencyBand": "H50", "location": "Studio A"}
            return None

        mock_make_request.side_effect = mock_make_request_side_effect

        device_data = {"id": "device1", "name": "Test Device"}
        result = client._enrich_device_data("device1", device_data)

        self.assertEqual(result["serial_number"], "ABC123")
        self.assertEqual(result["firmware_version"], "2.0.0")
        self.assertEqual(result["hostname"], "device1.local")
        self.assertEqual(result["mac_address"], "00:11:22:33:44:55")
        self.assertEqual(result["frequency_band"], "H50")
        self.assertEqual(result["location"], "Studio A")

    @patch("micboard.manufacturers.shure.client.ShureSystemAPIClient.get_devices")
    @patch("micboard.manufacturers.shure.client.ShureSystemAPIClient.get_device")
    @patch("micboard.manufacturers.shure.client.ShureSystemAPIClient.get_device_channels")
    @patch("micboard.manufacturers.shure.client.ShureSystemAPIClient._enrich_device_data")
    @patch("micboard.manufacturers.shure.transformers.ShureDataTransformer.transform_device_data")
    def test_poll_all_devices_success(
        self, mock_transform, mock_enrich, mock_get_channels, mock_get_device, mock_get_devices
    ):
        """Test successful polling of all devices"""
        mock_get_devices.return_value = [{"id": "device1"}, {"id": "device2"}]
        mock_get_device.return_value = {"id": "device1", "name": "Device 1"}
        mock_get_channels.return_value = [{"channel": 1}]
        mock_enrich.return_value = {"id": "device1", "name": "Device 1", "enriched": True}
        mock_transform.return_value = {"id": "device1", "name": "Device 1", "transformed": True}

        client = ShureSystemAPIClient()
        result = client.poll_all_devices()

        self.assertEqual(len(result), 2)
        self.assertIn("device1", result)
        self.assertIn("device2", result)
        self.assertEqual(
            result["device1"], {"id": "device1", "name": "Device 1", "transformed": True}
        )

    @patch("micboard.manufacturers.shure.client.ShureSystemAPIClient.get_devices")
    def test_poll_all_devices_get_devices_failure(self, mock_get_devices):
        """Test poll_all_devices when get_devices fails"""
        mock_get_devices.side_effect = ShureAPIError("API unavailable")

        client = ShureSystemAPIClient()
        result = client.poll_all_devices()

        self.assertEqual(result, {})

    @patch("micboard.manufacturers.shure.client.ShureSystemAPIClient.get_devices")
    @patch("micboard.manufacturers.shure.client.ShureSystemAPIClient.get_device")
    def test_poll_all_devices_device_failure(self, mock_get_device, mock_get_devices):
        """Test poll_all_devices when individual device fails"""
        mock_get_devices.return_value = [{"id": "device1"}, {"id": "device2"}]
        mock_get_device.side_effect = ShureAPIError("Device unavailable")

        client = ShureSystemAPIClient()
        result = client.poll_all_devices()

        # Should return empty dict when devices fail
        self.assertEqual(result, {})

    @patch("micboard.manufacturers.shure.client.ShureSystemAPIClient.get_devices")
    @patch("micboard.manufacturers.shure.client.ShureSystemAPIClient.get_device")
    @patch("micboard.manufacturers.shure.transformers.ShureDataTransformer.transform_device_data")
    def test_poll_all_devices_transform_failure(
        self, mock_transform, mock_get_device, mock_get_devices
    ):
        """Test poll_all_devices when transformation fails"""
        mock_get_devices.return_value = [{"id": "device1"}]
        mock_get_device.return_value = {"id": "device1", "name": "Device 1"}
        mock_transform.return_value = None  # Transform fails

        client = ShureSystemAPIClient()
        result = client.poll_all_devices()

        # Should not include failed transformations
        self.assertEqual(result, {})

    @patch("micboard.manufacturers.shure.websocket.connect_and_subscribe")
    async def test_connect_and_subscribe(self, mock_connect):
        """Test WebSocket connection and subscription"""
        mock_connect.return_value = "connection_result"

        client = ShureSystemAPIClient()

        # Capture the callback in a variable so the same function object
        # is used when asserting the mock was called with it.
        def callback(x):
            pass

        result = await client.connect_and_subscribe("device1", callback)

        self.assertEqual(result, "connection_result")
        mock_connect.assert_called_once_with(client, "device1", callback)
