"""Receiver-browse projection, access, and pagination contracts."""

from __future__ import annotations

from django.contrib.auth.models import User
from django.http import QueryDict
from django.test import TestCase

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.locations.structure import Building, Location, Room
from micboard.models.monitoring.group import MonitoringGroup
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.hardware.receiver_browse_dtos import ReceiverBrowseCriteria
from micboard.services.hardware.receiver_browse_service import ReceiverBrowseService


class ReceiverBrowseServiceTests(TestCase):
    """The service must bound results and scope assignment-derived filters."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="receiver-browser")
        self.visible_group = MonitoringGroup.objects.create(name="Visible Receivers")
        self.visible_group.users.add(self.user)
        self.hidden_group = MonitoringGroup.objects.create(name="Hidden Receivers")

        self.building = Building.objects.create(name="Receiver Building")
        self.room = Room.objects.create(building=self.building, name="Receiver Room")
        self.location = Location.objects.create(
            building=self.building,
            room=self.room,
            name="Receiver Rack",
        )
        self.visible_group.locations.add(self.location)
        self.manufacturer = Manufacturer.objects.create(
            name="Receiver Manufacturer",
            code="receiver-manufacturer",
        )
        self.chassis = self._create_chassis(number=0, name="Visible Receiver")

    def _create_chassis(self, *, number: int, name: str) -> WirelessChassis:
        return WirelessChassis.objects.create(
            manufacturer=self.manufacturer,
            api_device_id=f"receiver-{number}",
            serial_number=f"receiver-serial-{number}",
            role="receiver",
            model="RX-4",
            name=name,
            ip=f"2001:db8:77::{number + 1}",
            location=self.location,
            status="online",
            is_online=True,
            max_channels=0,
        )

    def _assign(
        self,
        *,
        group: MonitoringGroup,
        performer_name: str,
        priority: str,
        active: bool = True,
    ) -> Performer:
        performer = Performer.objects.create(name=performer_name)
        unit = WirelessUnit.objects.create(
            base_chassis=self.chassis,
            manufacturer=self.manufacturer,
            serial_number=f"unit-{performer_name}",
            name=f"Unit {performer_name}",
            slot=PerformerAssignment.objects.count() + 1,
        )
        PerformerAssignment.objects.create(
            performer=performer,
            wireless_unit=unit,
            monitoring_group=group,
            priority=priority,
            is_active=active,
        )
        return performer

    def test_page_maps_prefetched_rows_without_extra_queries(self) -> None:
        criteria = ReceiverBrowseCriteria(title="All chassis")

        with self.assertNumQueries(2):
            page = ReceiverBrowseService.get_page(
                user=self.user,
                criteria=criteria,
                query_params=QueryDict(),
            )

        self.assertEqual(page.total_count, 1)
        self.assertEqual(page.items[0].name, "Visible Receiver")
        self.assertEqual(page.items[0].manufacturer_name, self.manufacturer.name)
        self.assertEqual(page.items[0].building_name, self.building.name)
        self.assertEqual(page.items[0].room_name, self.room.name)

    def test_hidden_or_inactive_assignments_cannot_match_browse_filters(self) -> None:
        hidden_performer = self._assign(
            group=self.hidden_group,
            performer_name="Hidden Performer",
            priority="critical",
        )
        inactive_performer = self._assign(
            group=self.visible_group,
            performer_name="Inactive Performer",
            priority="critical",
            active=False,
        )

        for criteria in (
            ReceiverBrowseCriteria(title="Priority", priority="critical"),
            ReceiverBrowseCriteria(title="Hidden", performer_id=hidden_performer.pk),
            ReceiverBrowseCriteria(title="Inactive", performer_id=inactive_performer.pk),
        ):
            with self.subTest(criteria=criteria):
                page = ReceiverBrowseService.get_page(
                    user=self.user,
                    criteria=criteria,
                    query_params=QueryDict(),
                )
                self.assertEqual(page.total_count, 0)

    def test_visible_assignment_matches_priority_and_performer(self) -> None:
        performer = self._assign(
            group=self.visible_group,
            performer_name="Visible Performer",
            priority="critical",
        )

        for criteria in (
            ReceiverBrowseCriteria(title="Priority", priority="critical"),
            ReceiverBrowseCriteria(title="Performer", performer_id=performer.pk),
        ):
            with self.subTest(criteria=criteria):
                page = ReceiverBrowseService.get_page(
                    user=self.user,
                    criteria=criteria,
                    query_params=QueryDict(),
                )
                self.assertEqual([item.id for item in page.items], [self.chassis.pk])

    def test_pagination_is_bounded_and_preserves_filter_query(self) -> None:
        for number in range(1, ReceiverBrowseService.PAGE_SIZE + 1):
            self._create_chassis(number=number, name=f"Receiver {number:02d}")

        page = ReceiverBrowseService.get_page(
            user=self.user,
            criteria=ReceiverBrowseCriteria(
                title="All chassis",
                manufacturer_code=self.manufacturer.code,
            ),
            query_params=QueryDict(f"manufacturer={self.manufacturer.code}&page=2"),
        )

        self.assertEqual(page.total_count, ReceiverBrowseService.PAGE_SIZE + 1)
        self.assertEqual(page.page_number, 2)
        self.assertEqual(len(page.items), 1)
        self.assertTrue(page.has_previous)
        self.assertFalse(page.has_next)
        self.assertEqual(page.query_string, f"manufacturer={self.manufacturer.code}")
