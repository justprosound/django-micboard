"""Regression coverage for frequently refreshed monitoring views."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.charger import Charger, ChargerSlot
from micboard.models.hardware.display_wall import DisplayWall, WallSection
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.locations import Building, Location
from micboard.models.monitoring.alert import Alert
from micboard.models.monitoring.group import MonitoringGroup
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.chargers.charger_display_service import get_charging_stations_data
from micboard.services.core.charger_assignment import ChargerAssignmentService
from micboard.services.monitoring.connection_validation import ConnectionValidationService

User = get_user_model()


class AlertListQueryTests(TestCase):
    """Alert list queries must not grow with the number of rendered rows."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="alert-query-user")
        building = Building.objects.create(name="Alert Query Building")
        location = Location.objects.create(name="Alert Query Location", building=building)
        manufacturer = Manufacturer.objects.create(
            name="Alert Query Manufacturer",
            code="alert-query",
        )
        chassis = WirelessChassis.objects.create(
            manufacturer=manufacturer,
            api_device_id="alert-query-chassis",
            name="Alert Query Chassis",
            role="receiver",
            location=location,
            ip="192.0.2.80",
        )
        self.channel = chassis.rf_channels.get(channel_number=1)
        unit = WirelessUnit.objects.create(
            base_chassis=chassis,
            manufacturer=manufacturer,
            slot=1,
            serial_number="ALERT-QUERY-UNIT",
        )
        performer = Performer.objects.create(name="Alert Query Performer")
        group = MonitoringGroup.objects.create(name="Alert Query Group")
        group.users.add(self.user)
        self.assignment = PerformerAssignment.objects.create(
            performer=performer,
            wireless_unit=unit,
            monitoring_group=group,
        )
        self.client.force_login(self.user)

    def _create_alert(self, index: int) -> None:
        Alert.objects.create(
            channel=self.channel,
            user=self.user,
            assignment=self.assignment,
            alert_type="signal_loss",
            status="resolved",
            message=f"query-budget-alert-{index}",
        )

    def test_query_count_is_constant_as_alert_rows_grow(self) -> None:
        self._create_alert(1)
        with CaptureQueriesContext(connection) as small_context:
            small_response = self.client.get(reverse("micboard:alerts"), {"status": "all"})

        for index in range(2, 6):
            self._create_alert(index)
        with CaptureQueriesContext(connection) as large_context:
            large_response = self.client.get(reverse("micboard:alerts"), {"status": "all"})

        self.assertEqual(small_response.status_code, 200)
        self.assertEqual(large_response.status_code, 200)
        self.assertEqual(len(large_context), len(small_context))
        self.assertLessEqual(len(large_context), 10)


class ChargerDisplayQueryTests(TestCase):
    """Charger display serialization must retain the slot prefetch cache."""

    def setUp(self) -> None:
        self.user = User.objects.create_superuser(username="charger-query-admin")
        building = Building.objects.create(name="Charger Query Building")
        self.location = Location.objects.create(
            name="Charger Query Location",
            building=building,
        )

    def _add_charger(self, index: int) -> None:
        charger = Charger.objects.create(
            location=self.location,
            name=f"Query Charger {index}",
            serial_number=f"QUERY-CHARGER-{index}",
            order=index,
        )
        ChargerSlot.objects.create(charger=charger, slot_number=2)
        ChargerSlot.objects.create(charger=charger, slot_number=1)

    def test_query_count_is_constant_as_chargers_grow(self) -> None:
        self._add_charger(1)
        with CaptureQueriesContext(connection) as small_context:
            small_data = get_charging_stations_data(user=self.user)

        self._add_charger(2)
        self._add_charger(3)
        with CaptureQueriesContext(connection) as large_context:
            large_data = get_charging_stations_data(user=self.user)

        self.assertEqual(len(small_data), 1)
        self.assertEqual(len(large_data), 3)
        self.assertEqual(len(large_context), len(small_context))
        self.assertLessEqual(len(large_context), 2)
        self.assertEqual(
            [slot["slot_number"] for slot in large_data[0]["slots"]],
            [1, 2],
        )


class DisplayWallSnapshotQueryTests(TestCase):
    """Display-wall snapshots must bulk-load their full display graph."""

    def setUp(self) -> None:
        self.user = User.objects.create_superuser(username="wall-query-admin")
        building = Building.objects.create(name="Wall Query Building")
        self.location = Location.objects.create(name="Wall Query Location", building=building)
        self.wall = DisplayWall.objects.create(
            location=self.location,
            name="Wall Query Display",
            kiosk_id="wall-query-display",
        )
        self.manufacturer = Manufacturer.objects.create(
            name="Wall Query Manufacturer",
            code="wall-query",
        )
        self.chassis = WirelessChassis.objects.create(
            manufacturer=self.manufacturer,
            api_device_id="wall-query-chassis",
            name="Wall Query Chassis",
            role="receiver",
            location=self.location,
            ip="192.0.2.81",
        )
        self.group = MonitoringGroup.objects.create(name="Wall Query Group")

    def _add_topology(self, index: int) -> None:
        charger = Charger.objects.create(
            location=self.location,
            name=f"Wall Query Charger {index}",
            serial_number=f"WALL-QUERY-CHARGER-{index}",
        )
        serial_number = f"WALL-QUERY-UNIT-{index}"
        ChargerSlot.objects.create(
            charger=charger,
            slot_number=1,
            occupied=True,
            device_serial=serial_number,
        )
        section = WallSection.objects.create(
            wall=self.wall,
            name=f"Wall Query Section {index}",
            display_order=index,
        )
        section.chargers.add(charger)
        unit = WirelessUnit.objects.create(
            base_chassis=self.chassis,
            manufacturer=self.manufacturer,
            slot=index,
            serial_number=serial_number,
        )
        PerformerAssignment.objects.create(
            performer=Performer.objects.create(name=f"Wall Query Performer {index}"),
            wireless_unit=unit,
            monitoring_group=self.group,
        )

    def test_query_count_is_constant_as_wall_topology_grows(self) -> None:
        self._add_topology(1)
        with CaptureQueriesContext(connection) as small_context:
            small_data = ChargerAssignmentService.get_display_wall_data(
                self.wall.pk,
                user=self.user,
            )

        self._add_topology(2)
        self._add_topology(3)
        with CaptureQueriesContext(connection) as large_context:
            large_data = ChargerAssignmentService.get_display_wall_data(
                self.wall.pk,
                user=self.user,
            )

        self.assertEqual(len(small_data["sections"]), 1)
        self.assertEqual(len(large_data["sections"]), 3)
        self.assertEqual(len(large_context), len(small_context))
        self.assertLessEqual(len(large_context), 6)
        self.assertEqual(
            large_data["sections"][0]["performers"][0]["performers"][0]["performer_name"],
            "Wall Query Performer 1",
        )


class ChargerHealthRegressionTests(TestCase):
    """Missing heartbeats must produce a stable offline health response."""

    def test_missing_last_seen_is_offline_without_extra_slot_query(self) -> None:
        building = Building.objects.create(name="Health Query Building")
        location = Location.objects.create(name="Health Query Location", building=building)
        charger = Charger.objects.create(
            location=location,
            name="Never Seen Charger",
            serial_number="NEVER-SEEN",
            last_seen=None,
        )
        for slot_number in (3, 1, 2):
            ChargerSlot.objects.create(charger=charger, slot_number=slot_number)

        with CaptureQueriesContext(connection) as query_context:
            health = ConnectionValidationService.check_charger_health(charger.pk)

        self.assertEqual(len(query_context), 2)
        self.assertEqual(health["health"], "offline")
        self.assertFalse(health["connected"])
        self.assertIsNone(health["last_heartbeat_seconds_ago"])
        self.assertEqual([slot["slot_number"] for slot in health["slots"]], [1, 2, 3])


class KioskHealthQueryTests(TestCase):
    """The frequently refreshed kiosk-health endpoint must remain query-bounded."""

    def setUp(self) -> None:
        self.user = User.objects.create_superuser(username="kiosk-health-query-admin")
        building = Building.objects.create(name="Kiosk Health Query Building")
        self.location = Location.objects.create(
            name="Kiosk Health Query Location",
            building=building,
        )
        self.wall = DisplayWall.objects.create(
            location=self.location,
            name="Kiosk Health Query Wall",
            kiosk_id="kiosk-health-query-wall",
        )
        self.client.force_login(self.user)

    def _add_topology(self, index: int) -> None:
        charger = Charger.objects.create(
            location=self.location,
            name=f"Kiosk Health Charger {index}",
            serial_number=f"KIOSK-HEALTH-{index}",
            last_seen=timezone.now(),
        )
        ChargerSlot.objects.create(
            charger=charger,
            slot_number=1,
            occupied=True,
            battery_percent=100,
        )
        section = WallSection.objects.create(
            wall=self.wall,
            name=f"Kiosk Health Section {index}",
            display_order=index,
        )
        section.chargers.add(charger)

    def test_query_count_is_constant_as_wall_topology_grows(self) -> None:
        self._add_topology(1)
        url = reverse("micboard:kiosk_health", args=[self.wall.pk])
        with CaptureQueriesContext(connection) as small_context:
            small_response = self.client.get(url)

        self._add_topology(2)
        self._add_topology(3)
        with CaptureQueriesContext(connection) as large_context:
            large_response = self.client.get(url)

        self.assertEqual(small_response.status_code, 200)
        self.assertEqual(large_response.status_code, 200)
        self.assertEqual(len(large_context), len(small_context))
        self.assertLessEqual(len(large_context), 6)
        self.assertEqual(len(large_response.json()["chargers"]), 3)


class DisplayWallDetailRegressionTests(TestCase):
    """The metadata-only detail page must not build unused live snapshots."""

    def test_detail_page_skips_unused_display_and_health_aggregation(self) -> None:
        user = User.objects.create_superuser(username="wall-detail-admin")
        building = Building.objects.create(name="Wall Detail Building")
        location = Location.objects.create(name="Wall Detail Location", building=building)
        wall = DisplayWall.objects.create(
            location=location,
            name="Metadata Only Wall",
            kiosk_id="metadata-only-wall",
        )
        self.client.force_login(user)

        with (
            patch.object(ChargerAssignmentService, "get_display_wall_data") as display_mock,
            patch.object(ConnectionValidationService, "check_charger_health") as health_mock,
        ):
            response = self.client.get(reverse("micboard:display_wall_detail", args=[wall.pk]))

        self.assertEqual(response.status_code, 200)
        display_mock.assert_not_called()
        health_mock.assert_not_called()
