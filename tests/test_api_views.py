"""
Tests for micboard API views.
"""
import json
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from micboard.models import DiscoveredDevice, Group, MicboardConfig, Receiver, Transmitter
from micboard.views.api import (
    ConfigHandler,
    GroupUpdateHandler,
    api_discover,
    api_refresh,
    data_json,
)

User = get_user_model()


class DataJsonViewTest(TestCase):
    """Test data_json API view"""

    def setUp(self):
        self.factory = RequestFactory()
        self.device = Device.objects.create(
            ip="192.168.1.100",
            device_type="uhfr",
            channel=1,
            slot=1,
            name="Test Device",
        )
        self.transmitter = Transmitter.objects.create(
            device=self.device,
            slot=1,
            battery=75,
            audio_level=-10,
            rf_level=-50,
        )
        self.group = Group.objects.create(
            group_number=1,
            title="Test Group",
            slots=[1, 2, 3],
        )
        self.discovered = DiscoveredDevice.objects.create(
            ip="192.168.1.200",
            device_type="uhfr",
            channels=2,
        )
        self.config = MicboardConfig.objects.create(
            key="test_key",
            value="test_value",
        )

    def test_data_json_returns_device_data(self):
        """Test data_json returns correct device data structure"""
        request = self.factory.get("/api/data/")
        response = data_json(request)

        assert response.status_code == 200
        data = json.loads(response.content)

        # Check structure
        assert "receivers" in data
        assert "config" in data
        assert "discovered" in data
        assert "groups" in data

        # Check device data
        assert len(data["receivers"]) == 1
        device_data = data["receivers"][0]
        assert device_data["ip"] == "192.168.1.100"
        assert device_data["type"] == "uhfr"
        assert device_data["channel"] == 1
        assert device_data["slot"] == 1
        assert device_data["name"] == "Test Device"

        # Check transmitter data
        assert "tx" in device_data
        tx_data = device_data["tx"][0]
        assert tx_data["battery"] == 75
        assert tx_data["audio_level"] == -10
        assert tx_data["rf_level"] == -50

        # Check config data
        assert data["config"] == {"test_key": "test_value"}

        # Check discovered devices
        assert len(data["discovered"]) == 1
        disc_data = data["discovered"][0]
        assert disc_data["ip"] == "192.168.1.200"
        assert disc_data["type"] == "uhfr"
        assert disc_data["channels"] == 2

        # Check groups data
        assert len(data["groups"]) == 1
        group_data = data["groups"][0]
        assert group_data["group"] == 1
        assert group_data["title"] == "Test Group"
        assert group_data["slots"] == [1, 2, 3]
        assert not group_data["hide_charts"]


class ConfigHandlerTest(TestCase):
    """Test ConfigHandler view"""

    def setUp(self):
        self.factory = RequestFactory()

    def test_config_update_success(self):
        """Test successful config update"""
        data = {"test_key": "test_value", "another_key": "another_value"}
        request = self.factory.post(
            "/api/config/", data=json.dumps(data), content_type="application/json"
        )

        response = ConfigHandler.as_view()(request)
        assert response.status_code == 200

        data = json.loads(response.content)
        assert data["success"]

        # Check database
        config1 = MicboardConfig.objects.get(key="test_key")
        assert config1.value == "test_value"

        config2 = MicboardConfig.objects.get(key="another_key")
        assert config2.value == "another_value"

    def test_config_update_invalid_json(self):
        """Test config update with invalid JSON"""
        request = self.factory.post(
            "/api/config/", data="invalid json", content_type="application/json"
        )

        response = ConfigHandler.as_view()(request)
        assert response.status_code == 400

        data = json.loads(response.content)
        assert "error" in data


class GroupUpdateHandlerTest(TestCase):
    """Test GroupUpdateHandler view"""

    def setUp(self):
        self.factory = RequestFactory()

    def test_group_update_success(self):
        """Test successful group update"""
        data = {
            "group": 1,
            "title": "Updated Group",
            "slots": [1, 2, 3, 4],
            "hide_charts": True,
        }
        request = self.factory.post(
            "/api/group/", data=json.dumps(data), content_type="application/json"
        )

        response = GroupUpdateHandler.as_view()(request)
        assert response.status_code == 200

        data = json.loads(response.content)
        assert data["success"]

        # Check database
        group = Group.objects.get(group_number=1)
        assert group.title == "Updated Group"
        assert group.slots == [1, 2, 3, 4]
        assert group.hide_charts

    def test_group_update_invalid_json(self):
        """Test group update with invalid JSON"""
        request = self.factory.post(
            "/api/group/", data="invalid json", content_type="application/json"
        )

        response = GroupUpdateHandler.as_view()(request)
        assert response.status_code == 400

        data = json.loads(response.content)
        assert "error" in data


class ApiDiscoverViewTest(TestCase):
    """Test api_discover view"""

    def setUp(self):
        self.factory = RequestFactory()

    def test_discover_get_method_not_allowed(self):
        """Test GET request returns 405"""
        request = self.factory.get("/api/discover/")
        response = api_discover(request)

        assert response.status_code == 405
        data = json.loads(response.content)
        assert data["error"] == "POST required"

    @patch("micboard.views.api.ShureSystemAPIClient")
    def test_discover_success(self, mock_client_class):
        """Test successful device discovery"""
        mock_client = Mock()
        mock_client.discover_devices.return_value = [
            {
                "ip_address": "192.168.1.100",
                "type": "uhfr",
                "channel_count": 2,
            },
            {
                "ip_address": "192.168.1.101",
                "type": "qlxd",
                "channel_count": 1,
            },
        ]
        mock_client._map_device_type.side_effect = lambda x: x  # Return type as-is
        mock_client_class.return_value = mock_client

        request = self.factory.post("/api/discover/")
        response = api_discover(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"]
        assert data["discovered_count"] == 2

        # Check devices were saved
        device1 = DiscoveredDevice.objects.get(ip="192.168.1.100")
        assert device1.device_type == "uhfr"
        assert device1.channels == 2

        device2 = DiscoveredDevice.objects.get(ip="192.168.1.101")
        assert device2.device_type == "qlxd"
        assert device2.channels == 1

    @patch("micboard.views.api.ShureSystemAPIClient")
    def test_discover_client_error(self, mock_client_class):
        """Test discovery with client error"""
        mock_client = Mock()
        mock_client.discover_devices.side_effect = Exception("API Error")
        mock_client_class.return_value = mock_client

        request = self.factory.post("/api/discover/")
        response = api_discover(request)

        assert response.status_code == 500
        data = json.loads(response.content)
        assert "error" in data


class ApiRefreshViewTest(TestCase):
    """Test api_refresh view"""

    def setUp(self):
        self.factory = RequestFactory()

    def test_refresh_get_method_not_allowed(self):
        """Test GET request returns 405"""
        request = self.factory.get("/api/refresh/")
        response = api_refresh(request)

        assert response.status_code == 405
        data = json.loads(response.content)
        assert data["error"] == "POST required"

    @patch("micboard.views.api.ShureSystemAPIClient")
    @patch("micboard.views.api.cache")
    def test_refresh_success(self, mock_cache, mock_client_class):
        """Test successful data refresh"""
        mock_client = Mock()
        mock_client.poll_all_devices.return_value = [
            {"ip": "192.168.1.100", "status": "online"},
            {"ip": "192.168.1.101", "status": "online"},
        ]
        mock_client_class.return_value = mock_client

        request = self.factory.post("/api/refresh/")
        response = api_refresh(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"]
        assert data["device_count"] == 2
        assert "timestamp" in data

        # Check cache was cleared
        mock_cache.delete.assert_called_once_with("micboard_device_data")

    @patch("micboard.views.api.ShureSystemAPIClient")
    def test_refresh_client_error(self, mock_client_class):
        """Test refresh with client error"""
        mock_client = Mock()
        mock_client.poll_all_devices.side_effect = Exception("API Error")
        mock_client_class.return_value = mock_client

        request = self.factory.post("/api/refresh/")
        response = api_refresh(request)

        assert response.status_code == 500
        data = json.loads(response.content)
        assert "error" in data
