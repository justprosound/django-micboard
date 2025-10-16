"""
Tests for dashboard and API views.
"""

import json
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from micboard.models import (
    Alert,
    Channel,
    DeviceAssignment,
    DiscoveredDevice,
    Group,
    Location,
    Manufacturer,
    MicboardConfig,
    Receiver,
)


class DashboardViewsTest(TestCase):
    """Test dashboard views"""

    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Create test data
        self.location = Location.objects.create(building="Test Building", room="Test Room")
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
        self.channel = Channel.objects.create(
            receiver=self.receiver,
            channel_number=1,
            frequency=584.000,
        )
        self.assignment = DeviceAssignment.objects.create(
            user=self.user,
            channel=self.channel,
            location=self.location,
            priority=1,
        )

    def tearDown(self):
        cache.clear()

    def test_index_view(self):
        """Test main dashboard index view"""
        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "micboard/index.html")

        # Check context data
        self.assertIn("device_count", response.context)
        self.assertIn("group_count", response.context)
        self.assertIn("buildings", response.context)
        self.assertIn("rooms", response.context)
        self.assertIn("users", response.context)

        # Check that active receivers are counted
        self.assertEqual(response.context["device_count"], 1)

    def test_about_view(self):
        """Test about page view"""
        response = self.client.get(reverse("about"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "micboard/about.html")

    def test_device_type_view(self):
        """Test device type view"""
        response = self.client.get(reverse("device_type", kwargs={"device_type": "ULXD4D"}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "micboard/device_type_view.html")

        # Check context
        self.assertEqual(response.context["device_type"], "ULXD4D")
        self.assertIn(self.receiver, response.context["receivers"])

    def test_device_type_view_no_devices(self):
        """Test device type view with no matching devices"""
        response = self.client.get(reverse("device_type", kwargs={"device_type": "QLXD4"}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["receivers"]), 0)

    def test_building_view(self):
        """Test building view"""
        response = self.client.get(reverse("building", kwargs={"building_name": "Test Building"}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "micboard/building_view.html")

        # Check context
        self.assertEqual(response.context["building_name"], "Test Building")
        self.assertIn(self.receiver, response.context["receivers"])

    def test_user_view(self):
        """Test user view"""
        response = self.client.get(reverse("user", kwargs={"username": "testuser"}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "micboard/user_view.html")

        # Check context
        self.assertEqual(response.context["username"], "testuser")
        self.assertIn(self.receiver, response.context["receivers"])

    def test_room_view(self):
        """Test room view"""
        response = self.client.get(reverse("room", kwargs={"room_name": "Test Room"}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "micboard/room_view.html")

        # Check context
        self.assertEqual(response.context["room_name"], "Test Room")
        self.assertIn(self.receiver, response.context["receivers"])

    def test_priority_view(self):
        """Test priority view"""
        response = self.client.get(reverse("priority", kwargs={"priority": "1"}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "micboard/priority_view.html")

        # Check context
        self.assertEqual(response.context["priority"], "1")
        self.assertIn(self.receiver, response.context["receivers"])


class AlertViewsTest(TestCase):
    """Test alert-related views"""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", password="testpass")

        # Create test data
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

        # Create test alerts
        self.pending_alert = Alert.objects.create(
            alert_type="interference",
            severity="warning",
            message="Test interference alert",
            channel=self.channel,
            user=self.user,
            assignment=self.assignment,
            status="pending",
        )
        self.acknowledged_alert = Alert.objects.create(
            alert_type="battery_low",
            severity="info",
            message="Test battery alert",
            status="acknowledged",
        )

    def test_alerts_view_default(self):
        """Test alerts view with default filters"""
        response = self.client.get(reverse("alerts"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "micboard/alerts.html")

        # Check context
        self.assertIn("alerts", response.context)
        self.assertIn("stats", response.context)
        self.assertIn("alert_types", response.context)
        self.assertIn("alert_statuses", response.context)

        # Check stats
        stats = response.context["stats"]
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["pending"], 1)
        self.assertEqual(stats["acknowledged"], 1)

    def test_alerts_view_filtered_by_status(self):
        """Test alerts view filtered by status"""
        response = self.client.get(reverse("alerts") + "?status=acknowledged")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["alerts"]), 1)
        self.assertEqual(response.context["alerts"][0], self.acknowledged_alert)

    def test_alerts_view_filtered_by_type(self):
        """Test alerts view filtered by type"""
        response = self.client.get(reverse("alerts") + "?type=interference")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["alerts"]), 1)
        self.assertEqual(response.context["alerts"][0], self.pending_alert)

    def test_alert_detail_view(self):
        """Test alert detail view"""
        response = self.client.get(
            reverse("alert_detail", kwargs={"alert_id": self.pending_alert.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "micboard/alert_detail.html")
        self.assertEqual(response.context["alert"], self.pending_alert)

    def test_alert_detail_view_not_found(self):
        """Test alert detail view with non-existent alert"""
        response = self.client.get(reverse("alert_detail", kwargs={"alert_id": 999}))

        self.assertEqual(response.status_code, 404)

    def test_acknowledge_alert_view_get(self):
        """Test acknowledge alert view with GET request"""
        response = self.client.get(
            reverse("acknowledge_alert", kwargs={"alert_id": self.pending_alert.id})
        )

        # Should redirect to alert detail
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response, reverse("alert_detail", kwargs={"alert_id": self.pending_alert.id})
        )

    def test_acknowledge_alert_view_post(self):
        """Test acknowledge alert view with POST request"""
        self.client.login(username="testuser", password="testpass")
        response = self.client.post(
            reverse("acknowledge_alert", kwargs={"alert_id": self.pending_alert.id})
        )

        # Should redirect to alerts list
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("alerts"))

        # Check that alert was acknowledged
        self.pending_alert.refresh_from_db()
        self.assertEqual(self.pending_alert.status, "acknowledged")

    def test_resolve_alert_view_post(self):
        """Test resolve alert view with POST request"""
        self.client.login(username="testuser", password="testpass")
        response = self.client.post(
            reverse("resolve_alert", kwargs={"alert_id": self.pending_alert.id})
        )

        # Should redirect to alerts list
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("alerts"))

        # Check that alert was resolved
        self.pending_alert.refresh_from_db()
        self.assertEqual(self.pending_alert.status, "resolved")


class APIViewsTest(TestCase):
    """Test API views"""

    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()

        # Create test data
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
        cache.clear()

    @patch("micboard.views.api.serialize_receivers")
    def test_data_json_view(self, mock_serialize):
        """Test data.json API endpoint"""
        mock_serialize.return_value = [{"id": "TEST001", "name": "Test Receiver"}]

        response = self.client.get(reverse("data_json"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")

        data = response.json()
        self.assertIn("receivers", data)
        self.assertIn("config", data)
        self.assertIn("discovered", data)
        self.assertIn("groups", data)

    @patch("micboard.views.api.serialize_receivers")
    def test_data_json_cached(self, mock_serialize):
        """Test data.json returns cached data"""
        cached_data = {"receivers": [{"id": "CACHED"}], "cached": True}
        cache.set("micboard_device_data", cached_data)

        response = self.client.get(reverse("data_json"))

        # Should not call serializer
        mock_serialize.assert_not_called()

        data = response.json()
        self.assertEqual(data, cached_data)

    def test_config_handler_post(self):
        """Test config handler POST"""
        config_data = {"test_key": "test_value", "another_key": 123}

        response = self.client.post(
            reverse("config"),
            data=json.dumps(config_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        # Check config was saved
        config_obj = MicboardConfig.objects.get(key="test_key")
        self.assertEqual(config_obj.value, "test_value")

    def test_config_handler_invalid_json(self):
        """Test config handler with invalid JSON"""
        response = self.client.post(
            reverse("config"),
            data="invalid json",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_group_update_handler_post(self):
        """Test group update handler POST"""
        group_data = {
            "group": 1,
            "title": "Test Group",
            "slots": [1, 2, 3],
            "hide_charts": True,
        }

        response = self.client.post(
            reverse("group_update"),
            data=json.dumps(group_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        # Check group was created/updated
        group = Group.objects.get(group_number=1)
        self.assertEqual(group.title, "Test Group")

    @patch("micboard.views.api.ShureSystemAPIClient")
    def test_api_discover_post(self, mock_client_class):
        """Test device discovery API"""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_devices.return_value = [
            {
                "ip_address": "192.168.1.101",
                "type": "ULXD4D",
                "capabilities": [{"name": "channels", "count": 4}],
            }
        ]

        response = self.client.post(reverse("api_discover"))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["discovered_count"], 1)

        # Check device was saved
        device = DiscoveredDevice.objects.get(ip="192.168.1.101")
        self.assertEqual(device.device_type, "ULXD4D")
        self.assertEqual(device.channels, 4)

    def test_api_discover_get_method_not_allowed(self):
        """Test discovery API rejects GET requests"""
        response = self.client.get(reverse("api_discover"))

        self.assertEqual(response.status_code, 405)
        self.assertIn("POST required", response.json()["error"])

    @patch("micboard.views.api.ShureSystemAPIClient")
    def test_api_refresh_post(self, mock_client_class):
        """Test data refresh API"""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.poll_all_devices.return_value = {"status": "success"}

        response = self.client.post(reverse("api_refresh"))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("Polling triggered", data["message"])

        # Check cache was cleared
        self.assertIsNone(cache.get("micboard_device_data"))

    @patch("micboard.views.api.ShureSystemAPIClient")
    def test_api_health_view(self, mock_client_class):
        """Test health check API"""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.is_healthy.return_value = True

        response = self.client.get(reverse("api_health"))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["api_status"], "healthy")
        self.assertIn("database", data)
        self.assertIn("shure_api", data)

    def test_api_receiver_detail_view(self):
        """Test receiver detail API"""
        response = self.client.get(
            reverse("api_receiver_detail", kwargs={"receiver_id": "TEST001"})
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["api_device_id"], "TEST001")
        self.assertEqual(data["name"], "Test Receiver")

    def test_api_receiver_detail_not_found(self):
        """Test receiver detail API with non-existent receiver"""
        response = self.client.get(
            reverse("api_receiver_detail", kwargs={"receiver_id": "NONEXISTENT"})
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("Receiver not found", response.json()["error"])

    def test_api_receivers_list_view(self):
        """Test receivers list API"""
        response = self.client.get(reverse("api_receivers_list"))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("receivers", data)
        self.assertIn("count", data)
        self.assertEqual(data["count"], 1)

    def test_health_check_view(self):
        """Test detailed health check view"""
        response = self.client.get(reverse("health_check"))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("checks", data)
        self.assertIn("database", data["checks"])
        self.assertIn("cache", data["checks"])

    def test_readiness_check_view(self):
        """Test readiness check view"""
        response = self.client.get(reverse("readiness_check"))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ready")

    def test_api_documentation_view(self):
        """Test API documentation view"""
        response = self.client.get(reverse("api_documentation"))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("api_version", data)
        self.assertIn("endpoints", data)
        self.assertIn("versions", data)

        # Check that all expected endpoints are documented
        endpoints = data["endpoints"]
        self.assertIn("health", endpoints)
        self.assertIn("data", endpoints)
        self.assertIn("receivers", endpoints)
        self.assertIn("discover", endpoints)


class APIViewBaseTest(TestCase):
    """Test API view base classes"""

    def setUp(self):
        self.factory = RequestFactory()

    def test_api_view_version_headers(self):
        """Test that API views add version headers"""
        from micboard.views.api import APIView

        view = APIView()
        request = self.factory.get("/test/")

        # Mock dispatch to return a response
        with patch.object(view, "dispatch", return_value=MagicMock()) as mock_dispatch:
            mock_response = MagicMock()
            mock_dispatch.return_value = mock_response

            view.dispatch(request)

            # Check headers were added
            mock_response.__setitem__.assert_any_call("X-API-Version", "1.0.0")
            mock_response.__setitem__.assert_any_call("X-API-Compatible", "1.0.0")

    def test_versioned_api_view_version_negotiation(self):
        """Test version negotiation in VersionedAPIView"""
        from micboard.views.api import VersionedAPIView

        view = VersionedAPIView()

        # Test default version
        request = self.factory.get("/test/")
        self.assertEqual(view.get_api_version(request), "1.0.0")

        # Test query parameter version
        request = self.factory.get("/test/?version=1.1")
        self.assertEqual(view.get_api_version(request), "1.1")

        # Test Accept header version
        request = self.factory.get("/test/", HTTP_ACCEPT="application/json; version=2.0")
        self.assertEqual(view.get_api_version(request), "2.0")
