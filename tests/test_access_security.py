"""Regression tests for authorization-sensitive HTTP endpoints."""

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import DiscoveredDevice
from micboard.models.hardware.charger import Charger, ChargerSlot
from micboard.models.hardware.display_wall import DisplayWall, WallSection
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.locations import Building, Location
from micboard.models.monitoring.alert import Alert
from micboard.models.monitoring.group import MonitoringGroup
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.core.performer_assignment import PerformerAssignmentService


class AlertAccessTests(TestCase):
    """Alerts must remain private to their recipient."""

    def setUp(self) -> None:
        self.owner = User.objects.create_user(username="alert-owner", password="test-pass")
        self.other_user = User.objects.create_user(username="other-user", password="test-pass")
        manufacturer = Manufacturer.objects.create(name="Access Test", code="access-test")
        chassis = WirelessChassis.objects.create(
            manufacturer=manufacturer,
            api_device_id="access-test-chassis",
            role="receiver",
            ip="192.0.2.10",
        )
        channel = chassis.rf_channels.get(channel_number=1)
        self.owner_alert = Alert.objects.create(
            channel=channel,
            user=self.owner,
            alert_type="signal_loss",
            status="resolved",
            message="owner-only alert",
        )
        self.other_alert = Alert.objects.create(
            channel=channel,
            user=self.other_user,
            alert_type="signal_loss",
            status="resolved",
            message="other-user-only alert",
        )
        self.client = Client()
        self.client.force_login(self.owner)

    def test_alert_list_excludes_other_users_alerts(self) -> None:
        response = self.client.get(reverse("micboard:alerts"), {"status": "all"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.owner_alert.message)
        self.assertNotContains(response, self.other_alert.message)

    def test_alert_detail_hides_another_users_alert(self) -> None:
        response = self.client.get(reverse("micboard:alert_detail", args=[self.other_alert.pk]))

        self.assertEqual(response.status_code, 404)

    def test_alert_row_partial_hides_another_users_alert(self) -> None:
        response = self.client.get(
            reverse("micboard:alert_row_partial", args=[self.other_alert.pk])
        )

        self.assertEqual(response.status_code, 404)


class DiscoveredDevicePromotionAccessTests(TestCase):
    """Device promotion must use a permission-checked unsafe HTTP method."""

    def setUp(self) -> None:
        self.staff_user = User.objects.create_user(
            username="limited-staff",
            password="test-pass",
            is_staff=True,
        )
        self.discovered = DiscoveredDevice.objects.create(
            ip="192.0.2.20",
            device_type="receiver",
        )
        self.client = Client()
        self.client.force_login(self.staff_user)
        self.url = reverse(
            "admin:micboard_discoverdevice_promote",
            args=[self.discovered.pk],
        )

    @patch(
        "micboard.admin.monitoring.DiscoveredDeviceAdmin._promote_to_chassis",
        return_value=(False, "not promoted", None),
    )
    def test_get_does_not_promote_device(self, promote_mock) -> None:
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 405)
        promote_mock.assert_not_called()

    @patch(
        "micboard.admin.monitoring.DiscoveredDeviceAdmin._promote_to_chassis",
        return_value=(False, "not promoted", None),
    )
    def test_post_requires_all_promotion_permissions(self, promote_mock) -> None:
        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 403)
        promote_mock.assert_not_called()

    @patch(
        "micboard.admin.monitoring.DiscoveredDeviceAdmin._promote_to_chassis",
        return_value=(False, "not promoted", None),
    )
    def test_post_requires_csrf_token(self, promote_mock) -> None:
        superuser = User.objects.create_superuser(
            username="promotion-superuser",
            password="test-pass",
        )
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(superuser)

        response = csrf_client.post(self.url)

        self.assertEqual(response.status_code, 403)
        promote_mock.assert_not_called()


class PerformerAssignmentAccessTests(TestCase):
    """Assignment writes must validate every referenced object against user scope."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="assignment-user", password="test-pass")
        other_user = User.objects.create_user(username="other-assignment-user")

        self.group = MonitoringGroup.objects.create(name="Assignment Group")
        self.group.users.add(self.user)
        other_group = MonitoringGroup.objects.create(name="Other Assignment Group")
        other_group.users.add(other_user)

        own_building = Building.objects.create(name="Assignment Building")
        own_location = Location.objects.create(
            building=own_building,
            name="Assignment Location",
        )
        self.group.locations.add(own_location)

        other_building = Building.objects.create(name="Other Assignment Building")
        other_location = Location.objects.create(
            building=other_building,
            name="Other Assignment Location",
        )
        other_group.locations.add(other_location)

        manufacturer = Manufacturer.objects.create(
            name="Assignment Manufacturer",
            code="assignment-manufacturer",
        )
        self.own_chassis = WirelessChassis.objects.create(
            manufacturer=manufacturer,
            api_device_id="assignment-chassis",
            role="receiver",
            ip="192.0.2.30",
            location=own_location,
        )
        other_chassis = WirelessChassis.objects.create(
            manufacturer=manufacturer,
            api_device_id="other-assignment-chassis",
            role="receiver",
            ip="192.0.2.31",
            location=other_location,
        )
        self.unit = WirelessUnit.objects.create(
            base_chassis=self.own_chassis,
            manufacturer=manufacturer,
            slot=1,
            name="Assignment Unit",
        )
        self.other_unit = WirelessUnit.objects.create(
            base_chassis=other_chassis,
            manufacturer=manufacturer,
            slot=1,
            name="Other Assignment Unit",
        )
        self.performer = Performer.objects.create(name="Assignment Performer")
        self.unassigned_performer = Performer.objects.create(name="Unassigned Performer")
        self.other_performer = Performer.objects.create(name="Other Assignment Performer")
        PerformerAssignment.objects.create(
            performer=self.performer,
            wireless_unit=self.unit,
            monitoring_group=self.group,
        )
        self.other_assignment = PerformerAssignment.objects.create(
            performer=self.other_performer,
            wireless_unit=self.other_unit,
            monitoring_group=other_group,
        )

        self.client.force_login(self.user)

    def test_create_form_lists_only_user_scoped_objects(self) -> None:
        response = self.client.get(reverse("micboard:create_assignment"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.performer.name)
        self.assertContains(response, self.unit.name)
        self.assertContains(response, self.group.name)
        self.assertNotContains(response, self.other_performer.name)
        self.assertNotContains(response, self.other_unit.name)
        self.assertNotContains(response, self.other_assignment.monitoring_group.name)

    def test_invalid_create_rerenders_form(self) -> None:
        response = self.client.post(reverse("micboard:create_assignment"), {})

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Performer, Wireless Unit, and Monitoring Group are required",
        )

    def test_unassigned_performer_can_receive_first_assignment(self) -> None:
        unassigned_unit = WirelessUnit.objects.create(
            base_chassis=self.own_chassis,
            manufacturer=self.unit.manufacturer,
            slot=2,
            name="Unassigned Unit",
        )

        form_response = self.client.get(reverse("micboard:create_assignment"))
        create_response = self.client.post(
            reverse("micboard:create_assignment"),
            {
                "performer_id": self.unassigned_performer.pk,
                "wireless_unit_id": unassigned_unit.pk,
                "monitoring_group_id": self.group.pk,
            },
        )

        self.assertContains(form_response, self.unassigned_performer.name)
        self.assertRedirects(create_response, reverse("micboard:assignments"))
        self.assertTrue(
            PerformerAssignment.objects.filter(
                performer=self.unassigned_performer,
                wireless_unit=unassigned_unit,
            ).exists()
        )

    def test_create_rejects_performer_from_another_scope(self) -> None:
        response = self.client.post(
            reverse("micboard:create_assignment"),
            {
                "performer_id": self.other_performer.pk,
                "wireless_unit_id": self.unit.pk,
                "monitoring_group_id": self.group.pk,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            PerformerAssignment.objects.filter(
                performer=self.other_performer,
                wireless_unit=self.unit,
            ).exists()
        )

    def test_create_rejects_wireless_unit_from_another_scope(self) -> None:
        response = self.client.post(
            reverse("micboard:create_assignment"),
            {
                "performer_id": self.performer.pk,
                "wireless_unit_id": self.other_unit.pk,
                "monitoring_group_id": self.group.pk,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            PerformerAssignment.objects.filter(
                performer=self.performer,
                wireless_unit=self.other_unit,
            ).exists()
        )

    def test_superuser_can_create_assignment_across_scopes(self) -> None:
        superuser = User.objects.create_superuser(
            username="assignment-superuser",
            password="test-pass",
        )
        self.client.force_login(superuser)

        response = self.client.post(
            reverse("micboard:create_assignment"),
            {
                "performer_id": self.other_performer.pk,
                "wireless_unit_id": self.unit.pk,
                "monitoring_group_id": self.group.pk,
            },
        )

        self.assertRedirects(response, reverse("micboard:assignments"))
        self.assertTrue(
            PerformerAssignment.objects.filter(
                performer=self.other_performer,
                wireless_unit=self.unit,
                monitoring_group=self.group,
            ).exists()
        )

    def test_service_rejects_cross_scope_assignment_update(self) -> None:
        with self.assertRaises(PerformerAssignment.DoesNotExist):
            PerformerAssignmentService.update_assignment(
                assignment_id=self.other_assignment.pk,
                user=self.user,
                notes="cross-scope update",
            )

        self.other_assignment.refresh_from_db()
        self.assertNotEqual(self.other_assignment.notes, "cross-scope update")

    def test_service_rejects_cross_scope_assignment_delete(self) -> None:
        deleted = PerformerAssignmentService.delete_assignment(
            assignment_id=self.other_assignment.pk,
            user=self.user,
        )

        self.assertFalse(deleted)
        self.assertTrue(PerformerAssignment.objects.filter(pk=self.other_assignment.pk).exists())


class ChargerAndKioskAuthenticationTests(TestCase):
    """Operational displays must not expose hardware or performer data anonymously."""

    def test_charger_display_requires_login(self) -> None:
        response = self.client.get(reverse("micboard:charger_display"))

        self.assertRedirects(
            response,
            f"{settings.LOGIN_URL}?next={reverse('micboard:charger_display')}",
            fetch_redirect_response=False,
        )

    def test_kiosk_display_requires_login(self) -> None:
        building = Building.objects.create(name="Kiosk Authentication Building")
        location = Location.objects.create(
            building=building,
            name="Kiosk Authentication Location",
        )
        wall = DisplayWall.objects.create(
            location=location,
            name="Kiosk Authentication Wall",
            kiosk_id="kiosk-authentication-wall",
        )

        response = self.client.get(reverse("micboard:kiosk_display", args=[wall.kiosk_id]))

        self.assertRedirects(
            response,
            f"{settings.LOGIN_URL}?next={reverse('micboard:kiosk_display', args=[wall.kiosk_id])}",
            fetch_redirect_response=False,
        )


class ChargerAndKioskScopeTests(TestCase):
    """Charger and display-wall endpoints must honor monitoring-group locations."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="display-user", password="test-pass")
        self.superuser = User.objects.create_superuser(
            username="display-superuser",
            password="test-pass",
        )
        group = MonitoringGroup.objects.create(name="Display Group")
        group.users.add(self.user)

        own_building = Building.objects.create(name="Display Building")
        self.own_location = Location.objects.create(
            building=own_building,
            name="Owned Display Location",
        )
        group.locations.add(self.own_location)

        foreign_building = Building.objects.create(name="Foreign Display Building")
        self.foreign_location = Location.objects.create(
            building=foreign_building,
            name="Foreign Display Location",
        )

        self.own_charger = Charger.objects.create(
            location=self.own_location,
            name="Owned Charger",
            serial_number="OWN-CHARGER",
            ip="192.0.2.40",
            status="online",
            last_seen=timezone.now(),
        )
        self.foreign_charger = Charger.objects.create(
            location=self.foreign_location,
            name="Foreign Charger",
            serial_number="FOREIGN-CHARGER",
            ip="192.0.2.41",
            status="online",
            last_seen=timezone.now(),
        )
        ChargerSlot.objects.create(
            charger=self.own_charger,
            slot_number=1,
            occupied=True,
            device_model="OWNED-MIC",
        )
        ChargerSlot.objects.create(
            charger=self.foreign_charger,
            slot_number=1,
            occupied=True,
            device_model="FOREIGN-MIC",
        )

        self.own_wall = DisplayWall.objects.create(
            location=self.own_location,
            name="Owned Wall",
            kiosk_id="owned-wall",
        )
        self.foreign_wall = DisplayWall.objects.create(
            location=self.foreign_location,
            name="Foreign Wall",
            kiosk_id="foreign-wall",
        )
        self.own_section = WallSection.objects.create(
            wall=self.own_wall,
            name="Owned Section",
        )
        self.own_section.chargers.add(self.own_charger, self.foreign_charger)
        self.foreign_section = WallSection.objects.create(
            wall=self.foreign_wall,
            name="Foreign Section",
        )
        self.foreign_section.chargers.add(self.foreign_charger)

        self.client.force_login(self.user)

    def test_charger_display_excludes_foreign_location(self) -> None:
        response = self.client.get(reverse("micboard:charger_display"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.own_charger.name)
        self.assertNotContains(response, self.foreign_charger.name)
        self.assertNotContains(response, "FOREIGN-MIC")

    def test_foreign_display_wall_routes_return_not_found(self) -> None:
        urls = [
            reverse("micboard:display_wall_detail", args=[self.foreign_wall.pk]),
            reverse("micboard:wall_section_list", args=[self.foreign_wall.pk]),
            reverse("micboard:kiosk_data", args=[self.foreign_wall.pk]),
            reverse("micboard:kiosk_health", args=[self.foreign_wall.pk]),
            reverse("micboard:kiosk_display", args=[self.foreign_wall.kiosk_id]),
            reverse("micboard:wall_section_partial", args=[self.foreign_section.pk]),
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_wall_health_excludes_cross_linked_foreign_charger(self) -> None:
        response = self.client.get(reverse("micboard:kiosk_health", args=[self.own_wall.pk]))

        self.assertEqual(response.status_code, 200)
        charger_ids = {item["charger"]["id"] for item in response.json()["chargers"]}
        self.assertEqual(charger_ids, {self.own_charger.pk})

    def test_superuser_can_access_foreign_display_wall(self) -> None:
        self.client.force_login(self.superuser)

        response = self.client.get(
            reverse("micboard:kiosk_display", args=[self.foreign_wall.kiosk_id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.foreign_wall.name)
