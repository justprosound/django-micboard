"""Authorization regression tests for custom admin and settings endpoints."""

from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse

from micboard.admin.discovery_admin import DiscoveryQueueAdmin
from micboard.admin.monitoring import DiscoveredDeviceAdmin
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.queue import DiscoveryQueue
from micboard.models.discovery.registry import DiscoveredDevice
from micboard.models.hardware.wireless_chassis import WirelessChassis


class CustomAdminPermissionTests(TestCase):
    """Custom admin URLs must enforce their model's permissions."""

    def setUp(self) -> None:
        self.staff_user = User.objects.create_user(
            username="unrelated-staff",
            password="test-pass",
            is_staff=True,
        )
        self.manufacturer = Manufacturer.objects.create(
            name="Admin Permission Manufacturer",
            code="admin-permission-manufacturer",
        )
        self.client.force_login(self.staff_user)

    def test_hardware_layout_requires_wireless_chassis_view_permission(self) -> None:
        response = self.client.get(reverse("admin:micboard_wireless_chassis_hardware_layout"))

        self.assertEqual(response.status_code, 403)

    def test_discovery_ips_requires_manufacturer_view_permission(self) -> None:
        response = self.client.get(
            reverse(
                "admin:micboard_manufacturer_discovery_ips",
                args=[self.manufacturer.pk],
            )
        )

        self.assertEqual(response.status_code, 403)

    @patch("micboard.admin.manufacturers.DiscoveryService.remove_discovery_candidate")
    def test_discovery_ip_removal_requires_change_permission(self, remove_mock) -> None:
        view_permission = Permission.objects.get(
            content_type__app_label="micboard",
            codename="view_manufacturer",
        )
        self.staff_user.user_permissions.add(view_permission)

        response = self.client.post(
            reverse(
                "admin:micboard_manufacturer_discovery_ips",
                args=[self.manufacturer.pk],
            ),
            {"remove_ip": "192.0.2.80"},
        )

        self.assertEqual(response.status_code, 403)
        remove_mock.assert_not_called()

    def test_remote_delete_action_requires_delete_permission(self) -> None:
        change_permission = Permission.objects.get(
            content_type__app_label="micboard",
            codename="change_discovereddevice",
        )
        self.staff_user.user_permissions.add(change_permission)
        request = RequestFactory().get("/admin/micboard/discovereddevice/")
        request.user = self.staff_user
        model_admin = DiscoveredDeviceAdmin(DiscoveredDevice, admin.site)

        actions = model_admin.get_actions(request)

        self.assertNotIn("delete_and_remove_from_api", actions)

    def test_discovery_approval_requires_target_model_permissions(self) -> None:
        queue_item = DiscoveryQueue.objects.create(
            manufacturer=self.manufacturer,
            api_device_id="permission-test-device",
            serial_number="PERMISSION-TEST-DEVICE",
            ip="192.0.2.81",
            device_type="receiver",
        )
        request = RequestFactory().post("/admin/micboard/discoveryqueue/")
        request.user = self.staff_user
        model_admin = DiscoveryQueueAdmin(DiscoveryQueue, admin.site)

        with self.assertRaises(PermissionDenied):
            model_admin.approve_devices(
                request,
                DiscoveryQueue.objects.filter(pk=queue_item.pk),
            )

        self.assertFalse(
            WirelessChassis.objects.filter(serial_number=queue_item.serial_number).exists()
        )


class SettingsEndpointPermissionTests(TestCase):
    """Staff status alone must not expose stored setting overrides."""

    def test_settings_diff_requires_setting_view_permission(self) -> None:
        staff_user = User.objects.create_user(
            username="settings-unrelated-staff",
            password="test-pass",
            is_staff=True,
        )
        self.client.force_login(staff_user)

        response = self.client.get(reverse("micboard:settings_diff"))

        self.assertEqual(response.status_code, 403)
