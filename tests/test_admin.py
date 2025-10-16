"""
Tests for Django admin interfaces.
"""

from unittest.mock import MagicMock, patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from micboard.admin.assignments import AlertAdmin, DeviceAssignmentAdmin, UserAlertPreferenceAdmin
from micboard.admin.devices import ChannelAdmin, ReceiverAdmin, TransmitterAdmin
from micboard.admin.monitoring import (
    DiscoveredDeviceAdmin,
    GroupAdmin,
    LocationAdmin,
    MicboardConfigAdmin,
    MonitoringGroupAdmin,
)
from micboard.models import (
    Alert,
    Channel,
    DeviceAssignment,
    DiscoveredDevice,
    Group,
    Location,
    Manufacturer,
    MicboardConfig,
    MonitoringGroup,
    Receiver,
    Transmitter,
    UserAlertPreference,
)


class DeviceAdminTest(TestCase):
    """Test device-related admin interfaces"""

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()

        # Create test data
        self.user = User.objects.create_user(
            username="admin", password="pass", is_staff=True, is_superuser=True
        )
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
        )
        self.transmitter = Transmitter.objects.create(
            channel=self.channel,
            slot=1,
            frequency="584.000",
            battery=191,  # 75% of 255
        )

    def test_receiver_admin_list_display(self):
        """Test ReceiverAdmin list display"""
        admin = ReceiverAdmin(Receiver, self.site)

        # Test list_display fields
        self.assertIn("name", admin.list_display)
        self.assertIn("device_type", admin.list_display)
        self.assertIn("status_indicator", admin.list_display)

        # Test status_indicator method
        indicator = admin.status_indicator(self.receiver)
        self.assertIn("Online", indicator)
        self.assertIn("green", indicator)

        # Test with inactive receiver
        self.receiver.is_active = False
        indicator = admin.status_indicator(self.receiver)
        self.assertIn("Offline", indicator)
        self.assertIn("red", indicator)

    def test_receiver_admin_actions(self):
        """Test ReceiverAdmin actions"""
        admin = ReceiverAdmin(Receiver, self.site)
        request = self.factory.get("/admin/")
        request.user = self.user

        # Test mark_online action
        queryset = Receiver.objects.filter(pk=self.receiver.pk)
        admin.mark_online(request, queryset)

        self.receiver.refresh_from_db()
        self.assertTrue(self.receiver.is_active)

        # Test mark_offline action
        admin.mark_offline(request, queryset)
        self.receiver.refresh_from_db()
        self.assertFalse(self.receiver.is_active)

    @patch("micboard.admin.devices.ShureSystemAPIClient")
    def test_receiver_admin_sync_action(self, mock_client_class):
        """Test ReceiverAdmin sync_from_api action"""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.get_device.return_value = {
            "name": "Updated Receiver",
            "firmware": "2.0.0",
        }

        admin = ReceiverAdmin(Receiver, self.site)
        request = self.factory.get("/admin/")
        request.user = self.user

        queryset = Receiver.objects.filter(pk=self.receiver.pk)
        admin.sync_from_api(request, queryset)

        self.receiver.refresh_from_db()
        self.assertEqual(self.receiver.name, "Updated Receiver")
        self.assertEqual(self.receiver.firmware_version, "2.0.0")
        self.assertTrue(self.receiver.is_active)

    def test_channel_admin_list_display(self):
        """Test ChannelAdmin list display"""
        admin = ChannelAdmin(Channel, self.site)

        # Test list_display fields
        self.assertIn("__str__", admin.list_display)
        self.assertIn("has_transmitter", admin.list_display)

        # Test has_transmitter method
        indicator = admin.has_transmitter(self.channel)
        self.assertIn("Yes", indicator)
        self.assertIn("Slot 1", indicator)

        # Test channel without transmitter
        channel_no_tx = Channel.objects.create(
            receiver=self.receiver,
            channel_number=2,
        )
        indicator = admin.has_transmitter(channel_no_tx)
        self.assertIn("No", indicator)

    def test_transmitter_admin_list_display(self):
        """Test TransmitterAdmin list display"""
        admin = TransmitterAdmin(Transmitter, self.site)

        # Test list_display fields
        self.assertIn("__str__", admin.list_display)
        self.assertIn("battery_indicator", admin.list_display)

        # Test battery_indicator method
        indicator = admin.battery_indicator(self.transmitter)
        self.assertIn("75%", indicator)
        self.assertIn("green", indicator)  # > 50%

        # Test low battery
        self.transmitter.battery_percentage = 5
        indicator = admin.battery_indicator(self.transmitter)
        self.assertIn("5%", indicator)
        self.assertIn("red", indicator)  # <= 10%

        # Test unknown battery
        self.transmitter.battery_percentage = None
        indicator = admin.battery_indicator(self.transmitter)
        self.assertIn("Unknown", indicator)
        self.assertIn("gray", indicator)


class AssignmentAdminTest(TestCase):
    """Test assignment-related admin interfaces"""

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()

        # Create test data
        self.user = User.objects.create_user(username="testuser", password="testpass")
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
        )
        self.channel = Channel.objects.create(
            receiver=self.receiver,
            channel_number=1,
        )
        self.assignment = DeviceAssignment.objects.create(
            user=self.user,
            channel=self.channel,
            location=self.location,
            priority=1,
        )
        self.alert = Alert.objects.create(
            alert_type="battery_low",
            severity="warning",
            message="Battery low",
            channel=self.channel,
            user=self.user,
            assignment=self.assignment,
            status="pending",
        )

    def test_device_assignment_admin_list_display(self):
        """Test DeviceAssignmentAdmin list display"""
        admin = DeviceAssignmentAdmin(DeviceAssignment, self.site)

        # Test list_display fields
        self.assertIn("user", admin.list_display)
        self.assertIn("channel", admin.list_display)
        self.assertIn("priority", admin.list_display)

    def test_alert_admin_list_display(self):
        """Test AlertAdmin list display"""
        admin = AlertAdmin(Alert, self.site)

        # Test list_display fields
        self.assertIn("channel", admin.list_display)
        self.assertIn("status_indicator", admin.list_display)

        # Test status_indicator method
        indicator = admin.status_indicator(self.alert)
        self.assertIn("Pending", indicator)
        self.assertIn("orange", indicator)

        # Test resolved alert
        self.alert.status = "resolved"
        indicator = admin.status_indicator(self.alert)
        self.assertIn("Resolved", indicator)
        self.assertIn("green", indicator)

    def test_alert_admin_actions(self):
        """Test AlertAdmin actions"""
        admin = AlertAdmin(Alert, self.site)
        request = self.factory.get("/admin/")
        request.user = self.user

        # Test acknowledge_alerts action
        queryset = Alert.objects.filter(pk=self.alert.pk)
        admin.acknowledge_alerts(request, queryset)

        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, "acknowledged")

        # Test resolve_alerts action
        admin.resolve_alerts(request, queryset)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, "resolved")

    def test_user_alert_preference_admin_list_display(self):
        """Test UserAlertPreferenceAdmin list display"""
        admin = UserAlertPreferenceAdmin(UserAlertPreference, self.site)

        # Test list_display fields
        self.assertIn("user", admin.list_display)
        self.assertIn("notification_method", admin.list_display)


class MonitoringAdminTest(TestCase):
    """Test monitoring-related admin interfaces"""

    def setUp(self):
        self.site = AdminSite()

        # Create test data
        self.manufacturer = Manufacturer.objects.create(
            code="shure", name="Shure Incorporated", config={"api_url": "http://test.com"}
        )
        self.group = Group.objects.create(
            group_number=1,
            title="Test Group",
            hide_charts=False,
        )
        self.config = MicboardConfig.objects.create(
            key="test_config",
            value="test_value",
        )
        self.discovered_device = DiscoveredDevice.objects.create(
            ip="192.168.1.101",
            device_type="ULXD4D",
            channels=4,
            manufacturer=self.manufacturer,
        )
        self.location = Location.objects.create(
            building="Test Building",
            room="Test Room",
        )
        self.monitoring_group = MonitoringGroup.objects.create(
            name="Test Monitoring Group",
            location=self.location,
            is_active=True,
        )

    def test_group_admin_list_display(self):
        """Test GroupAdmin list display"""
        admin = GroupAdmin(Group, self.site)

        # Test list_display fields
        self.assertIn("group_number", admin.list_display)
        self.assertIn("title", admin.list_display)

    def test_micboard_config_admin_list_display(self):
        """Test MicboardConfigAdmin list display"""
        admin = MicboardConfigAdmin(MicboardConfig, self.site)

        # Test list_display fields
        self.assertIn("key", admin.list_display)
        self.assertIn("value", admin.list_display)

    def test_discovered_device_admin_list_display(self):
        """Test DiscoveredDeviceAdmin list display"""
        admin = DiscoveredDeviceAdmin(DiscoveredDevice, self.site)

        # Test list_display fields
        self.assertIn("ip", admin.list_display)
        self.assertIn("device_type", admin.list_display)
        self.assertIn("channels", admin.list_display)

    def test_location_admin_list_display(self):
        """Test LocationAdmin list display"""
        admin = LocationAdmin(Location, self.site)

        # Test list_display fields
        self.assertIn("name", admin.list_display)
        self.assertIn("building", admin.list_display)
        self.assertIn("room", admin.list_display)

    def test_monitoring_group_admin_list_display(self):
        """Test MonitoringGroupAdmin list display"""
        admin = MonitoringGroupAdmin(MonitoringGroup, self.site)

        # Test list_display fields
        self.assertIn("name", admin.list_display)
        self.assertIn("location", admin.list_display)
        self.assertIn("is_active", admin.list_display)


class AdminInlineTest(TestCase):
    """Test admin inline configurations"""

    def setUp(self):
        self.site = AdminSite()

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
        )
        self.transmitter = Transmitter.objects.create(
            channel=self.channel,
            slot=1,
            frequency="584.000",
        )

    def test_channel_inline_configuration(self):
        """Test ChannelInline configuration"""
        from micboard.admin.devices import ChannelInline

        inline = ChannelInline(Channel, self.site)

        # Test inline configuration
        self.assertEqual(inline.model, Channel)
        self.assertEqual(inline.extra, 1)
        self.assertIn("get_transmitter_status", inline.readonly_fields)

        # Test get_transmitter_status method
        status = inline.get_transmitter_status(self.channel)
        self.assertIn("Slot 1", status)
        self.assertIn("Battery", status)

        # Test channel without transmitter
        channel_no_tx = Channel.objects.create(
            receiver=self.receiver,
            channel_number=2,
        )
        status = inline.get_transmitter_status(channel_no_tx)
        self.assertEqual(status, "No transmitter assigned")

    def test_transmitter_inline_configuration(self):
        """Test TransmitterInline configuration"""
        from micboard.admin.devices import TransmitterInline

        inline = TransmitterInline(Transmitter, self.site)

        # Test inline configuration
        self.assertEqual(inline.model, Transmitter)
        self.assertEqual(inline.extra, 1)
        self.assertIn("battery_percentage", inline.readonly_fields)
        self.assertIn("updated_at", inline.readonly_fields)
