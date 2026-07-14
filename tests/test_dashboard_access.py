"""Authorization regression tests for dashboard and object-fragment views."""

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.locations import Building, Location, Room
from micboard.models.monitoring.group import MonitoringGroup


class DashboardAccessTests(TestCase):
    """Dashboard topology and device fragments must honor monitoring scope."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="dashboard-user", password="test-pass")
        other_user = User.objects.create_user(username="other-dashboard-user")

        own_group = MonitoringGroup.objects.create(name="Dashboard Group")
        own_group.users.add(self.user)
        other_group = MonitoringGroup.objects.create(name="Other Dashboard Group")
        other_group.users.add(other_user)

        self.own_building = Building.objects.create(name="Accessible Building")
        self.own_room = Room.objects.create(building=self.own_building, name="Accessible Room")
        self.own_location = Location.objects.create(
            building=self.own_building,
            room=self.own_room,
            name="Accessible Location",
        )
        own_group.locations.add(self.own_location)

        self.foreign_building = Building.objects.create(name="Foreign Building")
        self.foreign_room = Room.objects.create(
            building=self.foreign_building,
            name="Foreign Room",
        )
        self.foreign_location = Location.objects.create(
            building=self.foreign_building,
            room=self.foreign_room,
            name="Foreign Location",
        )
        other_group.locations.add(self.foreign_location)

        manufacturer = Manufacturer.objects.create(
            name="Dashboard Manufacturer",
            code="dashboard-manufacturer",
        )
        own_chassis = WirelessChassis.objects.create(
            manufacturer=manufacturer,
            api_device_id="dashboard-own-chassis",
            role="receiver",
            ip="192.0.2.70",
            location=self.own_location,
        )
        foreign_chassis = WirelessChassis.objects.create(
            manufacturer=manufacturer,
            api_device_id="dashboard-foreign-chassis",
            role="receiver",
            ip="192.0.2.71",
            location=self.foreign_location,
        )
        self.own_channel = own_chassis.rf_channels.get(channel_number=1)
        self.foreign_channel = foreign_chassis.rf_channels.get(channel_number=1)

    def test_operational_dashboard_routes_require_login(self) -> None:
        urls = [
            reverse("micboard:index"),
            reverse("micboard:all_buildings_view"),
            reverse("micboard:single_building_view", args=[self.own_building.name]),
            reverse(
                "micboard:room_view",
                args=[self.own_building.name, self.own_room.name],
            ),
            reverse("micboard:device_type_view", args=["all"]),
            reverse("micboard:priority_view", args=["all"]),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(f"{settings.LOGIN_URL}?next="))

    def test_building_and_room_lists_exclude_foreign_topology(self) -> None:
        self.client.force_login(self.user)

        buildings_response = self.client.get(reverse("micboard:all_buildings_view"))
        self.assertEqual(buildings_response.status_code, 200)
        self.assertContains(buildings_response, self.own_building.name)
        self.assertNotContains(buildings_response, self.foreign_building.name)

        rooms_response = self.client.get(reverse("micboard:room_view", args=["all", "all"]))
        self.assertEqual(rooms_response.status_code, 200)
        self.assertContains(rooms_response, self.own_room.name)
        self.assertNotContains(rooms_response, self.foreign_room.name)

    def test_foreign_building_and_room_routes_return_not_found(self) -> None:
        self.client.force_login(self.user)

        urls = [
            reverse("micboard:single_building_view", args=[self.foreign_building.name]),
            reverse(
                "micboard:room_view",
                args=[self.foreign_building.name, self.foreign_room.name],
            ),
        ]

        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_channel_partial_rejects_cross_group_id(self) -> None:
        self.client.force_login(self.user)

        own_response = self.client.get(
            reverse("micboard:channel_card_partial", args=[self.own_channel.pk])
        )
        foreign_response = self.client.get(
            reverse("micboard:channel_card_partial", args=[self.foreign_channel.pk])
        )

        self.assertEqual(own_response.status_code, 200)
        self.assertEqual(foreign_response.status_code, 404)


class DashboardSuperuserAccessTests(TestCase):
    """Superusers retain the system-wide topology view."""

    def test_superuser_can_view_unassigned_building(self) -> None:
        superuser = User.objects.create_superuser(
            username="dashboard-superuser",
            password="test-pass",
        )
        building = Building.objects.create(name="Unassigned Building")
        client = Client()
        client.force_login(superuser)

        response = client.get(reverse("micboard:all_buildings_view"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, building.name)
