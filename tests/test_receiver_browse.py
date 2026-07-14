"""Rendered receiver-browse route contracts."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.locations.structure import Building, Location, Room
from micboard.models.monitoring.group import MonitoringGroup
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment


class ReceiverBrowseRequestTests(TestCase):
    """Real templates must render only chassis and assignments visible to the user."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="browse-user")
        self.other_user = User.objects.create_user(username="other-browse-user")
        self.visible_group = MonitoringGroup.objects.create(name="Browse Group")
        self.visible_group.users.add(self.user)
        self.hidden_group = MonitoringGroup.objects.create(name="Hidden Browse Group")
        self.hidden_group.users.add(self.other_user)

        self.visible_building = Building.objects.create(name="Shared Building Name")
        self.visible_room = Room.objects.create(
            building=self.visible_building,
            name="Visible Room",
        )
        self.visible_location = Location.objects.create(
            building=self.visible_building,
            room=self.visible_room,
            name="Visible Rack",
        )
        self.visible_group.locations.add(self.visible_location)

        self.hidden_building = Building.objects.create(name="Shared Building Name")
        self.hidden_room = Room.objects.create(
            building=self.hidden_building,
            name="Hidden Room",
        )
        self.hidden_location = Location.objects.create(
            building=self.hidden_building,
            room=self.hidden_room,
            name="Hidden Rack",
        )
        self.hidden_group.locations.add(self.hidden_location)

        self.manufacturer = Manufacturer.objects.create(
            name="Browse Manufacturer",
            code="browse-manufacturer",
        )
        self.visible_chassis = self._create_chassis(
            name="Visible Browser Chassis",
            identifier="visible-browser",
            ip="192.0.2.210",
            location=self.visible_location,
        )
        self.hidden_chassis = self._create_chassis(
            name="Hidden Browser Chassis",
            identifier="hidden-browser",
            ip="192.0.2.211",
            location=self.hidden_location,
        )
        self.client.force_login(self.user)

    def _create_chassis(
        self,
        *,
        name: str,
        identifier: str,
        ip: str,
        location: Location,
    ) -> WirelessChassis:
        return WirelessChassis.objects.create(
            manufacturer=self.manufacturer,
            api_device_id=identifier,
            role="receiver",
            model="Browser RX",
            name=name,
            ip=ip,
            location=location,
            status="online",
            is_online=True,
            max_channels=0,
        )

    def test_role_building_and_room_routes_render_visible_chassis(self) -> None:
        urls = [
            reverse("micboard:device_type_view", args=["receiver"]),
            reverse("micboard:single_building_view", args=[self.visible_building.pk]),
            reverse("micboard:room_view", args=[self.visible_room.pk]),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, "micboard/receiver_browse.html")
                self.assertContains(response, self.visible_chassis.name)
                self.assertNotContains(response, self.hidden_chassis.name)

    def test_duplicate_building_names_are_unambiguous_and_foreign_ids_are_hidden(self) -> None:
        visible_response = self.client.get(
            reverse("micboard:single_building_view", args=[self.visible_building.pk])
        )
        hidden_response = self.client.get(
            reverse("micboard:single_building_view", args=[self.hidden_building.pk])
        )

        self.assertEqual(visible_response.status_code, 200)
        self.assertContains(visible_response, self.visible_chassis.name)
        self.assertEqual(hidden_response.status_code, 404)

    def test_priority_and_performer_routes_use_visible_active_assignments(self) -> None:
        performer = Performer.objects.create(name="Visible Browse Performer")
        unit = WirelessUnit.objects.create(
            base_chassis=self.visible_chassis,
            manufacturer=self.manufacturer,
            serial_number="visible-browse-unit",
            name="Visible Browse Unit",
            slot=1,
        )
        PerformerAssignment.objects.create(
            performer=performer,
            wireless_unit=unit,
            monitoring_group=self.visible_group,
            priority="critical",
        )

        for url in (
            reverse("micboard:priority_view", args=["critical"]),
            reverse("micboard:performer_view", args=[performer.pk]),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, self.visible_chassis.name)
                self.assertNotContains(response, self.hidden_chassis.name)

    def test_foreign_performer_and_invalid_choices_return_not_found(self) -> None:
        hidden_performer = Performer.objects.create(name="Hidden Browse Performer")
        hidden_unit = WirelessUnit.objects.create(
            base_chassis=self.hidden_chassis,
            manufacturer=self.manufacturer,
            serial_number="hidden-browse-unit",
            name="Hidden Browse Unit",
            slot=1,
        )
        PerformerAssignment.objects.create(
            performer=hidden_performer,
            wireless_unit=hidden_unit,
            monitoring_group=self.hidden_group,
        )

        urls = [
            reverse("micboard:performer_view", args=[hidden_performer.pk]),
            reverse("micboard:device_type_view", args=["unknown-role"]),
            reverse("micboard:priority_view", args=["urgent"]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
