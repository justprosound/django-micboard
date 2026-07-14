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

    def test_view_only_discovery_user_cannot_run_mutating_actions(self) -> None:
        """View permission must not expose or execute queue mutation actions."""
        view_permission = Permission.objects.get(
            content_type__app_label="micboard",
            codename="view_discoveryqueue",
        )
        self.staff_user.user_permissions.add(view_permission)
        queue_item = DiscoveryQueue.objects.create(
            manufacturer=self.manufacturer,
            api_device_id="view-only-device",
            serial_number="VIEW-ONLY-DEVICE",
            ip="192.0.2.83",
            device_type="receiver",
        )
        request = RequestFactory().get("/admin/micboard/discoveryqueue/")
        request.user = self.staff_user
        model_admin = DiscoveryQueueAdmin(DiscoveryQueue, admin.site)

        actions = model_admin.get_actions(request)
        response = self.client.post(
            reverse("admin:micboard_discoveryqueue_changelist"),
            {
                "action": "approve_devices",
                "_selected_action": queue_item.pk,
                "index": "0",
            },
        )

        self.assertNotIn("approve_devices", actions)
        self.assertNotIn("reject_devices", actions)
        self.assertNotIn("mark_as_duplicate", actions)
        self.assertIn(response.status_code, {200, 302})
        queue_item.refresh_from_db()
        self.assertEqual(queue_item.status, "pending")
        self.assertFalse(
            WirelessChassis.objects.filter(serial_number=queue_item.serial_number).exists()
        )

    def test_registered_admin_actions_declare_required_permissions(self) -> None:
        """Every project admin action must opt into Django's permission filtering."""
        self.staff_user.is_superuser = True
        self.staff_user.save(update_fields={"is_superuser"})
        request = RequestFactory().get("/admin/")
        request.user = self.staff_user

        unguarded_actions = []
        for model, model_admin in admin.site._registry.items():
            if model._meta.app_label != "micboard":
                continue
            for action, action_name, _description in model_admin.get_actions(request).values():
                if not getattr(action, "allowed_permissions", ()):  # pragma: no branch
                    unguarded_actions.append(f"{model._meta.label}.{action_name}")

        self.assertEqual(unguarded_actions, [])

    def test_discovery_admin_form_and_search_reference_real_model_fields(self) -> None:
        """The discovery admin must render and search without stale queue fields."""
        self.staff_user.is_superuser = True
        self.staff_user.save(update_fields={"is_superuser"})
        queue_item = DiscoveryQueue.objects.create(
            manufacturer=self.manufacturer,
            api_device_id="admin-form-device",
            serial_number="ADMIN-FORM-DEVICE",
            ip="192.0.2.82",
            device_type="receiver",
        )
        request = RequestFactory().get(
            "/admin/micboard/discoveryqueue/",
            {"q": "ADMIN-FORM-DEVICE"},
        )
        request.user = self.staff_user
        model_admin = DiscoveryQueueAdmin(DiscoveryQueue, admin.site)

        form_class = model_admin.get_form(request, obj=queue_item)
        results, _ = model_admin.get_search_results(
            request,
            DiscoveryQueue.objects.all(),
            "ADMIN-FORM-DEVICE",
        )

        self.assertNotIn("mac_address", form_class.base_fields)
        self.assertQuerySetEqual(results, [queue_item])


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
