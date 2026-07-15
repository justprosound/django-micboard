"""Alert page and live-row fragment integration contracts."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.http import QueryDict
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.locations.structure import Building, Location, Room
from micboard.models.monitoring.alert import Alert
from micboard.models.monitoring.group import MonitoringGroup
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.monitoring.alert_browse_dtos import AlertBrowseCriteria
from micboard.services.monitoring.alert_browse_service import AlertBrowseService


class AlertLiveFragmentTests(TestCase):
    """Live refreshes must stay bounded, scoped, and free of statistics work."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(username="alert-fragment-user")
        other_user = User.objects.create_user(username="other-alert-fragment-user")
        self.group = MonitoringGroup.objects.create(name="Alert Fragment Group")
        self.group.users.add(self.user)
        other_group = MonitoringGroup.objects.create(name="Other Alert Fragment Group")
        other_group.users.add(other_user)

        manufacturer = Manufacturer.objects.create(
            name="Alert Fragment Manufacturer",
            code="alert-fragment-manufacturer",
        )
        self.channel, self.assignment = self._build_assignment_graph(
            group=self.group,
            manufacturer=manufacturer,
            suffix="visible",
        )
        foreign_channel, foreign_assignment = self._build_assignment_graph(
            group=other_group,
            manufacturer=manufacturer,
            suffix="foreign",
        )
        self._create_alert(
            channel=self.channel,
            assignment=self.assignment,
            user=self.user,
            message="visible fragment alert",
        )
        self._create_alert(
            channel=foreign_channel,
            assignment=foreign_assignment,
            user=other_user,
            message="foreign fragment alert",
        )
        self.client.force_login(self.user)

    @staticmethod
    def _build_assignment_graph(*, group, manufacturer, suffix: str):
        building = Building.objects.create(name=f"Alert {suffix} Building")
        room = Room.objects.create(building=building, name=f"Alert {suffix} Room")
        location = Location.objects.create(
            building=building,
            room=room,
            name=f"Alert {suffix} Rack",
        )
        group.locations.add(location)
        chassis = WirelessChassis.objects.create(
            manufacturer=manufacturer,
            api_device_id=f"alert-{suffix}-chassis",
            role="receiver",
            name=f"Alert {suffix} Chassis",
            ip="192.0.2.220" if suffix == "visible" else "192.0.2.221",
            location=location,
            max_channels=1,
        )
        channel = chassis.rf_channels.get(channel_number=1)
        unit = WirelessUnit.objects.create(
            base_chassis=chassis,
            manufacturer=manufacturer,
            assigned_resource=channel,
            serial_number=f"alert-{suffix}-unit",
            name=f"Alert {suffix} Unit",
            slot=1,
        )
        performer = Performer.objects.create(name=f"Alert {suffix} Performer")
        assignment = PerformerAssignment.objects.create(
            performer=performer,
            wireless_unit=unit,
            monitoring_group=group,
        )
        return channel, assignment

    @staticmethod
    def _create_alert(*, channel, assignment, user, message: str) -> Alert:
        return Alert.objects.create(
            channel=channel,
            assignment=assignment,
            user=user,
            alert_type="signal_loss",
            status="resolved",
            message=message,
        )

    def test_fragment_excludes_foreign_alerts_and_skips_statistics(self) -> None:
        with patch.object(AlertBrowseService, "get_stats") as get_stats:
            response = self.client.get(
                reverse("micboard:alert_rows"),
                {"status": "all", "type": "signal_loss", "page": 1},
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "micboard/partials/alert_rows.html")
        self.assertContains(response, "visible fragment alert")
        self.assertNotContains(response, "foreign fragment alert")
        get_stats.assert_not_called()

    def test_fragment_page_is_bounded_to_twenty_five_rows(self) -> None:
        for index in range(AlertBrowseService.PAGE_SIZE):
            self._create_alert(
                channel=self.channel,
                assignment=self.assignment,
                user=self.user,
                message=f"bounded alert {index}",
            )

        with CaptureQueriesContext(connection) as query_context:
            response = self.client.get(reverse("micboard:alert_rows"), {"status": "all"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["browse"].items), AlertBrowseService.PAGE_SIZE)
        self.assertTrue(response.context["browse"].has_next)
        self.assertContains(response, "bounded alert 24")
        alert_queries = [
            query["sql"]
            for query in query_context.captured_queries
            if Alert._meta.db_table in query["sql"]
        ]
        self.assertEqual(len(alert_queries), 1, alert_queries)
        self.assertNotIn("COUNT(", alert_queries[0].upper())
        self.assertIn(f"LIMIT {AlertBrowseService.PAGE_SIZE + 1}", alert_queries[0].upper())

    def test_page_projection_uses_two_queries_and_full_page_preserves_poll_state(self) -> None:
        for index in range(AlertBrowseService.PAGE_SIZE):
            self._create_alert(
                channel=self.channel,
                assignment=self.assignment,
                user=self.user,
                message=f"full page alert {index}",
            )

        with self.assertNumQueries(2):
            browse = AlertBrowseService.get_page(
                user=self.user,
                criteria=AlertBrowseCriteria(
                    status="resolved",
                    alert_type="signal_loss",
                    page="invalid",
                ),
            )
        self.assertEqual(browse.page_number, 1)
        self.assertEqual(browse.total_count, AlertBrowseService.PAGE_SIZE + 1)
        self.assertEqual(browse.total_pages, 2)
        self.assertTrue(browse.has_next)

        response = self.client.get(
            reverse("micboard:alerts"),
            QueryDict("status=resolved&type=signal_loss&page=1"),
        )
        self.assertContains(
            response,
            "status=resolved&amp;type=signal_loss&amp;page=1",
        )
