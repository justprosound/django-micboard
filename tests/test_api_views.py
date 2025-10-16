"""
Tests for API views in micboard.views.api.
"""

import json
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase
from django.views import View

from micboard.models import (
    Channel,
    DiscoveredDevice,
    Group,
    Manufacturer,
    MicboardConfig,
    Receiver,
    Transmitter,
)
from micboard.views.api import (
    APIDocumentationView,
    APIView,
    ConfigHandler,
    GroupUpdateHandler,
    HealthCheckView,
    ReadinessCheckView,
    VersionedAPIView,
    api_discover,
    api_health,
    api_receiver_detail,
    api_receivers_list,
    api_refresh,
    data_json,
)

# User = get_user_model()


class APIViewTest(TestCase):
    """Test the base APIView class"""

    def test_api_view_adds_version_headers(self):
        """Test that APIView adds version headers to responses"""
        view = APIView()
        view.API_VERSION = "1.0.0"

        # Create a mock response that behaves like HttpResponse
        mock_response = Mock()
        mock_response.__setitem__ = Mock()
        mock_response.get = Mock(return_value=None)

        # Mock the parent's dispatch method
        with patch.object(View, "dispatch", return_value=mock_response):
            request = Mock()
            view.dispatch(request)

            # Check that headers were added to the response
            mock_response.__setitem__.assert_any_call("X-API-Version", "1.0.0")
            mock_response.__setitem__.assert_any_call("X-API-Compatible", "1.0.0")
            mock_response.__setitem__.assert_any_call("X-API-Compatible", "1.0.0")
            mock_response.__setitem__.assert_any_call("Content-Type", "application/json")

    def test_api_view_preserves_existing_content_type(self):
        """Test that APIView doesn't override existing Content-Type"""
        view = APIView()

        with patch.object(APIView, "dispatch", return_value=Mock()) as mock_dispatch:
            mock_response = Mock()
            mock_response.__getitem__ = Mock(return_value=None)
            mock_response.get = Mock(return_value="text/html")
            mock_response.__setitem__ = Mock()
            mock_dispatch.return_value = mock_response

            request = Mock()
            view.dispatch(request)

            # Should not set Content-Type since it already exists
            calls = [call[0] for call in mock_response.__setitem__.call_args_list]
            self.assertNotIn("Content-Type", [call[0] for call in calls])


class VersionedAPIViewTest(TestCase):
    """Test the VersionedAPIView class"""

    def test_get_api_version_from_accept_header(self):
        """Test version extraction from Accept header"""
        view = VersionedAPIView()
        request = Mock()
        request.META = {"HTTP_ACCEPT": "application/json; version=1.1"}
        request.GET = {}

        version = view.get_api_version(request)
        self.assertEqual(version, "1.1")

    def test_get_api_version_from_query_param(self):
        """Test version extraction from query parameter"""
        view = VersionedAPIView()
        request = Mock()
        request.META = {}
        request.GET = {"version": "2.0"}

        version = view.get_api_version(request)
        self.assertEqual(version, "2.0")

    def test_get_api_version_default(self):
        """Test default version when no version specified"""
        view = VersionedAPIView()
        view.API_VERSION = "1.0.0"
        request = Mock()
        request.META = {}
        request.GET = {}

        version = view.get_api_version(request)
        self.assertEqual(version, "1.0.0")


class DataJsonViewTest(TestCase):
    """Test the data_json view function"""

    def setUp(self):
        # Create a manufacturer for the test
        self.manufacturer = Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
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
            battery=80,
        )

    def test_data_json_returns_data(self):
        """Test data_json returns proper data structure"""
        request = Mock()
        request.META = {}
        request.build_absolute_uri.return_value = "http://testserver/"

        response = data_json(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertIn("receivers", data)
        self.assertIn("url", data)
        self.assertIn("config", data)
        self.assertIn("discovered", data)
        self.assertIn("groups", data)
        self.assertEqual(data["url"], "http://testserver/")

    def test_data_json_with_cached_data(self):
        """Test data_json uses cached data when available"""
        cached_data = {"test": "cached"}
        cache.set("micboard_device_data", cached_data)

        request = Mock()
        request.META = {}
        response = data_json(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data, cached_data)

        # Clean up
        cache.delete("micboard_device_data")

    def test_data_json_error_handling(self):
        """Test data_json handles exceptions properly"""
        request = Mock()
        request.META = {}

        # Mock an exception in serialize_receivers
        with patch("micboard.views.api.serialize_receivers", side_effect=Exception("Test error")):
            response = data_json(request)
            self.assertEqual(response.status_code, 500)

            data = json.loads(response.content)
            self.assertIn("error", data)

    def test_data_json_manufacturer_filtering(self):
        """Test data_json filters by manufacturer"""
        # Create test manufacturer
        manufacturer = Manufacturer.objects.create(
            code="test", name="Test Manufacturer", config={"api_url": "http://test.com"}
        )

        # Create test receiver for this manufacturer
        Receiver.objects.create(
            api_device_id="test-device-001",
            manufacturer=manufacturer,
            ip="192.168.1.100",
            device_type="uhfr",
            name="Test Receiver",
            is_active=True,
        )

        # Create another receiver for different manufacturer
        other_manufacturer = Manufacturer.objects.create(
            code="other", name="Other Manufacturer", config={"api_url": "http://other.com"}
        )
        Receiver.objects.create(
            api_device_id="other-device-001",
            manufacturer=other_manufacturer,
            ip="192.168.1.101",
            device_type="qlxd",
            name="Other Receiver",
            is_active=True,
        )

        request = Mock()
        request.META = {}
        request.GET = {"manufacturer": "test"}
        request.build_absolute_uri.return_value = "http://testserver/"

        response = data_json(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertIn("receivers", data)

        # Should only include receivers from the test manufacturer
        receiver_ids = [r["api_device_id"] for r in data["receivers"]]
        self.assertIn("test-device-001", receiver_ids)
        self.assertNotIn("other-device-001", receiver_ids)


class ConfigHandlerTest(TestCase):
    """Test the ConfigHandler class"""

    def test_config_handler_post_success(self):
        """Test successful config update"""
        view = ConfigHandler()
        request = Mock()
        request.body = json.dumps({"test_key": "test_value"}).encode()

        response = view.post(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data["success"])

        # Check that config was saved
        config = MicboardConfig.objects.get(key="test_key")
        self.assertEqual(config.value, "test_value")

    def test_config_handler_post_invalid_json(self):
        """Test config handler with invalid JSON"""
        view = ConfigHandler()
        request = Mock()
        request.body = b"invalid json"

        response = view.post(request)
        self.assertEqual(response.status_code, 400)

        data = json.loads(response.content)
        self.assertIn("error", data)

    def test_config_handler_get_manufacturer_filtering(self):
        """Test config handler GET with manufacturer filtering"""
        # Create test manufacturer
        manufacturer = Manufacturer.objects.create(
            code="test", name="Test Manufacturer", config={"api_url": "http://test.com"}
        )

        # Create global config
        MicboardConfig.objects.create(key="global_setting", value="global_value", manufacturer=None)

        # Create manufacturer-specific config
        MicboardConfig.objects.create(
            key="manufacturer_setting", value="manufacturer_value", manufacturer=manufacturer
        )

        view = ConfigHandler()
        request = Mock()
        request.GET = {"manufacturer": "test"}

        response = view.get(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertIn("global_setting", data)
        self.assertEqual(data["global_setting"], "global_value")
        self.assertIn("manufacturer_setting", data)
        self.assertEqual(data["manufacturer_setting"], "manufacturer_value")

    def test_config_handler_get_no_manufacturer_filtering(self):
        """Test config handler GET without manufacturer filtering returns global configs"""
        # Create global config
        MicboardConfig.objects.create(key="global_setting", value="global_value", manufacturer=None)

        # Create manufacturer-specific config (should not be included)
        manufacturer = Manufacturer.objects.create(
            code="test", name="Test Manufacturer", config={"api_url": "http://test.com"}
        )
        MicboardConfig.objects.create(
            key="manufacturer_setting", value="manufacturer_value", manufacturer=manufacturer
        )

        view = ConfigHandler()
        request = Mock()
        request.GET = {}

        response = view.get(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertIn("global_setting", data)
        self.assertEqual(data["global_setting"], "global_value")
        self.assertNotIn("manufacturer_setting", data)

    def test_config_handler_post_manufacturer_filtering(self):
        """Test config handler POST with manufacturer filtering"""
        # Create test manufacturer
        manufacturer = Manufacturer.objects.create(
            code="test", name="Test Manufacturer", config={"api_url": "http://test.com"}
        )

        view = ConfigHandler()
        request = Mock()
        request.body = json.dumps({"test_key": "test_value"}).encode()
        request.GET = {"manufacturer": "test"}

        response = view.post(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data["success"])

        # Check that config was saved with manufacturer
        config = MicboardConfig.objects.get(key="test_key", manufacturer=manufacturer)
        self.assertEqual(config.value, "test_value")


class GroupUpdateHandlerTest(TestCase):
    """Test the GroupUpdateHandler class"""

    def test_group_update_handler_post_success(self):
        """Test successful group update"""
        view = GroupUpdateHandler()
        request = Mock()
        request.body = json.dumps(
            {"group": 1, "title": "Test Group", "slots": [1, 2, 3], "hide_charts": True}
        ).encode()

        response = view.post(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data["success"])

        # Check that group was saved
        group = Group.objects.get(group_number=1)
        self.assertEqual(group.title, "Test Group")
        self.assertEqual(group.slots, [1, 2, 3])
        self.assertTrue(group.hide_charts)

    def test_group_update_handler_post_invalid_json(self):
        """Test group handler with invalid JSON"""
        view = GroupUpdateHandler()
        request = Mock()
        request.body = b"invalid json"

        response = view.post(request)
        self.assertEqual(response.status_code, 400)

        data = json.loads(response.content)
        self.assertIn("error", data)


class ApiDiscoverTest(TestCase):
    """Test the api_discover function"""

    def test_api_discover_get_method_not_allowed(self):
        """Test api_discover rejects GET requests"""
        request = Mock()
        request.META = {}
        request.method = "GET"

        response = api_discover(request)
        self.assertEqual(response.status_code, 405)

        data = json.loads(response.content)
        self.assertIn("error", data)

    @patch("micboard.views.api.get_manufacturer_plugin")
    def test_api_discover_success(self, mock_get_plugin):
        """Test successful device discovery"""
        # Create a manufacturer for the test
        manufacturer = Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
        )

        # Mock plugin
        mock_plugin_class = Mock()
        mock_plugin = Mock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin.get_devices.return_value = [
            {
                "ip_address": "192.168.1.101",
                "type": "uhfr",
                "capabilities": [{"name": "channels", "count": 4}],
            }
        ]
        mock_plugin.transform_device_data.return_value = {
            "type": "uhfr",
            "ip": "192.168.1.101",
            "channels": [1, 2, 3, 4],
        }
        mock_get_plugin.return_value = mock_plugin_class

        request = Mock()
        request.META = {}
        request.method = "POST"

        response = api_discover(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data["success"])
        self.assertEqual(data["discovered_count"], 1)

        # Check that device was saved
        device = DiscoveredDevice.objects.get(ip="192.168.1.101")
        self.assertEqual(device.device_type, "uhfr")
        self.assertEqual(device.channels, 4)
        self.assertEqual(device.manufacturer, manufacturer)
        self.assertEqual(device.manufacturer, manufacturer)

    @patch("micboard.views.api.ShureSystemAPIClient")
    def test_api_discover_error_handling(self, mock_client_class):
        """Test api_discover handles exceptions"""
        mock_client_class.side_effect = Exception("API Error")

        request = Mock()
        request.META = {}
        request.method = "POST"

        response = api_discover(request)
        self.assertEqual(response.status_code, 500)

        data = json.loads(response.content)
        self.assertIn("error", data)

    @patch("micboard.views.api.get_manufacturer_plugin")
    def test_api_discover_manufacturer_filtering(self, mock_get_plugin):
        """Test api_discover with manufacturer filtering"""
        # Create test manufacturer
        manufacturer = Manufacturer.objects.create(
            code="test", name="Test Manufacturer", config={"api_url": "http://test.com"}
        )

        # Mock plugin
        mock_plugin_class = Mock()
        mock_plugin = Mock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin.get_devices.return_value = [
            {
                "ip_address": "192.168.1.101",
                "type": "uhfr",
                "capabilities": [{"name": "channels", "count": 4}],
            }
        ]
        mock_plugin.transform_device_data.return_value = {
            "type": "uhfr",
            "ip": "192.168.1.101",
            "channels": [1, 2, 3, 4],
        }
        mock_get_plugin.return_value = mock_plugin_class

        request = Mock()
        request.META = {}
        request.method = "POST"
        request.GET = {"manufacturer": "test"}

        response = api_discover(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data["success"])
        self.assertEqual(data["discovered_count"], 1)

        # Check that device was saved with manufacturer
        device = DiscoveredDevice.objects.get(ip="192.168.1.101")
        self.assertEqual(device.device_type, "uhfr")
        self.assertEqual(device.channels, 4)
        self.assertEqual(device.manufacturer, manufacturer)


class ApiRefreshTest(TestCase):
    """Test the api_refresh function"""

    def test_api_refresh_get_method_not_allowed(self):
        """Test api_refresh rejects GET requests"""
        request = Mock()
        request.META = {}
        request.method = "GET"

        response = api_refresh(request)
        self.assertEqual(response.status_code, 405)

        data = json.loads(response.content)
        self.assertIn("error", data)

    @patch("micboard.views.api.get_manufacturer_plugin")
    def test_api_discover_success(self, mock_get_plugin):
        """Test successful device discovery"""
        # Create a manufacturer for the test
        Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
        )

        # Mock plugin
        mock_plugin_class = Mock()
        mock_plugin = Mock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin.get_devices.return_value = [{"name": "Device 1"}]
        mock_get_plugin.return_value = mock_plugin_class

        request = Mock()
        request.META = {}
        request.method = "POST"

        response = api_refresh(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data["success"])
        self.assertIn("message", data)
        self.assertIn("timestamp", data)

    @patch("micboard.views.api.get_manufacturer_plugin")
    def test_api_refresh_error_handling(self, mock_get_plugin):
        """Test api_refresh handles exceptions"""
        mock_get_plugin.side_effect = Exception("Plugin Error")

        request = Mock()
        request.META = {}
        request.method = "POST"

        response = api_refresh(request)
        self.assertEqual(response.status_code, 500)

        data = json.loads(response.content)
        self.assertIn("error", data)

    @patch("micboard.views.api.get_manufacturer_plugin")
    def test_api_refresh_manufacturer_filtering(self, mock_get_plugin):
        """Test api_refresh with manufacturer filtering"""
        # Create test manufacturer
        manufacturer = Manufacturer.objects.create(
            code="test", name="Test Manufacturer", config={"api_url": "http://test.com"}
        )

        # Mock plugin
        mock_plugin_class = Mock()
        mock_plugin = Mock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin.get_devices.return_value = [{"name": "Device 1"}]
        mock_get_plugin.return_value = mock_plugin_class

        request = Mock()
        request.META = {}
        request.method = "POST"
        request.GET = {"manufacturer": "test"}

        response = api_refresh(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data["success"])
        self.assertIn("message", data)
        self.assertIn("timestamp", data)

        # Verify the plugin was created with the manufacturer
        mock_plugin_class.assert_called_once_with(manufacturer)


class ApiHealthTest(TestCase):
    """Test the api_health function"""

    def setUp(self):
        self.receiver = Receiver.objects.create(
            api_device_id="test-device-001",
            ip="192.168.1.100",
            device_type="uhfr",
            name="Test Receiver",
            is_active=True,
        )

    @patch("micboard.views.api.get_manufacturer_plugin")
    def test_api_health_success(self, mock_get_plugin):
        """Test successful health check"""
        # Create a manufacturer for the test
        Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
        )

        # Mock plugin
        mock_plugin_class = Mock()
        mock_plugin = Mock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin.check_health.return_value = {"status": "healthy"}
        mock_get_plugin.return_value = mock_plugin_class

        request = Mock()
        request.META = {}

        response = api_health(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data["api_status"], "healthy")
        self.assertIn("timestamp", data)
        self.assertIn("database", data)
        self.assertIn("manufacturers", data)
        self.assertEqual(data["database"]["receivers_total"], 1)
        self.assertEqual(data["database"]["receivers_active"], 1)

    @patch("micboard.views.api.get_manufacturer_plugin")
    def test_api_health_api_unavailable(self, mock_get_plugin):
        """Test health check when manufacturer plugin is unavailable"""
        mock_get_plugin.side_effect = Exception("Connection failed")

        request = Mock()
        request.META = {}

        response = api_health(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data["api_status"], "degraded")
        self.assertIn("manufacturers", data)

    @patch("micboard.views.api.get_manufacturer_plugin")
    def test_api_health_manufacturer_filtering(self, mock_get_plugin):
        """Test api_health with manufacturer filtering"""
        # Create test manufacturer and receiver
        manufacturer = Manufacturer.objects.create(
            code="test", name="Test Manufacturer", config={"api_url": "http://test.com"}
        )
        Receiver.objects.create(
            api_device_id="test-device-001",
            manufacturer=manufacturer,
            ip="192.168.1.100",
            device_type="uhfr",
            name="Test Receiver",
            is_active=True,
        )

        # Mock plugin
        mock_plugin_class = Mock()
        mock_plugin = Mock()
        mock_plugin_class.return_value = mock_plugin
        mock_plugin.check_health.return_value = {"status": "healthy"}
        mock_get_plugin.return_value = mock_plugin_class

        request = Mock()
        request.META = {}
        request.GET = {"manufacturer": "test"}

        response = api_health(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data["api_status"], "healthy")
        self.assertIn("timestamp", data)
        self.assertIn("database", data)
        self.assertIn("manufacturers", data)
        self.assertEqual(data["database"]["receivers_total"], 1)
        self.assertEqual(data["database"]["receivers_active"], 1)

        # Verify the plugin was created with the manufacturer
        mock_plugin_class.assert_called_once_with(manufacturer)


class ApiReceiverDetailTest(TestCase):
    """Test the api_receiver_detail function"""

    def setUp(self):
        # Create a manufacturer for the test
        self.manufacturer = Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
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

    def test_api_receiver_detail_success(self):
        """Test successful receiver detail retrieval"""
        request = Mock()
        request.META = {}

        response = api_receiver_detail(request, "test-device-001")
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data["api_device_id"], "test-device-001")
        self.assertEqual(data["name"], "Test Receiver")

    def test_api_receiver_detail_not_found(self):
        """Test receiver detail for non-existent receiver"""
        request = Mock()
        request.META = {}

        response = api_receiver_detail(request, "non-existent")
        self.assertEqual(response.status_code, 404)

        data = json.loads(response.content)
        self.assertIn("error", data)

    def test_api_receiver_detail_manufacturer_filtering(self):
        """Test receiver detail with manufacturer filtering"""
        # Create test manufacturer and receiver
        manufacturer = Manufacturer.objects.create(
            code="test", name="Test Manufacturer", config={"api_url": "http://test.com"}
        )
        receiver = Receiver.objects.create(
            api_device_id="test-device-001",
            manufacturer=manufacturer,
            ip="192.168.1.100",
            device_type="uhfr",
            name="Test Receiver",
        )
        Channel.objects.create(
            receiver=receiver,
            channel_number=1,
        )

        request = Mock()
        request.META = {}
        request.GET = {"manufacturer": "test"}

        response = api_receiver_detail(request, "test-device-001")
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data["api_device_id"], "test-device-001")
        self.assertEqual(data["name"], "Test Receiver")
        self.assertEqual(data["manufacturer_code"], "test")


class ApiReceiversListTest(TestCase):
    """Test the api_receivers_list function"""

    def setUp(self):
        # Create manufacturers for the test
        self.manufacturer1 = Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://shure.com"}
        )
        self.manufacturer2 = Manufacturer.objects.create(
            code="sennheiser", name="Sennheiser", config={"api_url": "http://sennheiser.com"}
        )
        self.receiver1 = Receiver.objects.create(
            api_device_id="test-device-001",
            manufacturer=self.manufacturer1,
            ip="192.168.1.100",
            device_type="uhfr",
            name="Receiver A",
        )
        self.receiver2 = Receiver.objects.create(
            api_device_id="test-device-002",
            manufacturer=self.manufacturer2,
            ip="192.168.1.101",
            device_type="qlxd",
            name="Receiver B",
        )

    def test_api_receivers_list_success(self):
        """Test successful receivers list retrieval"""
        request = Mock()
        request.META = {}

        response = api_receivers_list(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["receivers"]), 2)

        # Check ordering by name
        self.assertEqual(data["receivers"][0]["name"], "Receiver A")
        self.assertEqual(data["receivers"][1]["name"], "Receiver B")

    def test_api_receivers_list_manufacturer_filtering(self):
        """Test receivers list with manufacturer filtering"""
        # Create test manufacturers
        manufacturer1 = Manufacturer.objects.create(
            code="test1", name="Test Manufacturer 1", config={"api_url": "http://test1.com"}
        )
        manufacturer2 = Manufacturer.objects.create(
            code="test2", name="Test Manufacturer 2", config={"api_url": "http://test2.com"}
        )

        # Create receivers for different manufacturers
        Receiver.objects.create(
            api_device_id="test-device-001",
            manufacturer=manufacturer1,
            ip="192.168.1.100",
            device_type="uhfr",
            name="Receiver A",
        )
        Receiver.objects.create(
            api_device_id="test-device-002",
            manufacturer=manufacturer2,
            ip="192.168.1.101",
            device_type="qlxd",
            name="Receiver B",
        )

        request = Mock()
        request.META = {}
        request.GET = {"manufacturer": "test1"}

        response = api_receivers_list(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data["count"], 1)
        self.assertEqual(len(data["receivers"]), 1)
        self.assertEqual(data["receivers"][0]["name"], "Receiver A")
        self.assertEqual(data["receivers"][0]["manufacturer_code"], "test1")


class HealthCheckViewTest(TestCase):
    """Test the HealthCheckView class"""

    def test_health_check_view_get_success(self):
        """Test successful health check view"""
        view = HealthCheckView()
        request = Mock()
        request.META = {}
        request.GET = {}

        response = view.get(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data["status"], "healthy")
        self.assertIn("timestamp", data)
        self.assertIn("version", data)
        self.assertIn("checks", data)
        self.assertIn("database", data["checks"])
        self.assertIn("cache", data["checks"])
        self.assertIn("shure_api_client", data["checks"])

    @patch("django.db.connection.cursor")
    def test_health_check_view_database_failure(self, mock_cursor):
        """Test health check when database fails"""
        mock_cursor.side_effect = Exception("DB Error")

        view = HealthCheckView()
        request = Mock()
        request.META = {}
        request.GET = {}

        response = view.get(request)
        self.assertEqual(response.status_code, 503)

        data = json.loads(response.content)
        self.assertEqual(data["status"], "unhealthy")
        self.assertEqual(data["checks"]["database"]["status"], "unhealthy")


class ReadinessCheckViewTest(TestCase):
    """Test the ReadinessCheckView class"""

    def test_readiness_check_view_get_success(self):
        """Test successful readiness check"""
        view = ReadinessCheckView()
        request = Mock()
        request.META = {}
        request.GET = {}

        response = view.get(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data["status"], "ready")
        self.assertIn("timestamp", data)
        self.assertIn("api_version", data)

    @patch("django.db.connection.cursor")
    def test_readiness_check_view_database_failure(self, mock_cursor):
        """Test readiness check when database fails"""
        mock_cursor.side_effect = Exception("DB Error")

        view = ReadinessCheckView()
        request = Mock()
        request.META = {}
        request.GET = {}

        response = view.get(request)
        self.assertEqual(response.status_code, 503)

        data = json.loads(response.content)
        self.assertEqual(data["status"], "not ready")


class APIDocumentationViewTest(TestCase):
    """Test the APIDocumentationView class"""

    def test_api_documentation_view_get(self):
        """Test API documentation view returns proper documentation"""
        view = APIDocumentationView()
        request = Mock()
        request.META = {}
        request.GET = {}
        request.build_absolute_uri.return_value = "http://testserver/api/"

        response = view.get(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertIn("api_version", data)
        self.assertIn("app_version", data)
        self.assertIn("base_url", data)
        self.assertIn("endpoints", data)
        self.assertIn("versions", data)
        self.assertIn("authentication", data)
        self.assertIn("rate_limiting", data)

        # Check that all expected endpoints are documented
        endpoints = data["endpoints"]
        expected_endpoints = [
            "health",
            "health_detailed",
            "health_ready",
            "data",
            "receivers",
            "receiver_detail",
            "discover",
            "refresh",
            "config",
            "group_update",
        ]
        for endpoint in expected_endpoints:
            self.assertIn(endpoint, endpoints)

    def test_api_documentation_view_version_negotiation(self):
        """Test API documentation respects version negotiation"""
        view = APIDocumentationView()
        request = Mock()
        request.META = {"HTTP_ACCEPT": "application/json; version=2.0"}
        request.GET = {}
        request.build_absolute_uri.return_value = "http://testserver/api/"

        response = view.get(request)
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data["api_version"], "2.0")
