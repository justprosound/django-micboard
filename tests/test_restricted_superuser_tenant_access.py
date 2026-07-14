"""Restricted-superuser tenant isolation regression tests."""

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings
from django.urls import reverse

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.locations import Building, Location, Room
from micboard.models.monitoring.alert import Alert
from micboard.models.monitoring.group import MonitoringGroup
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.models.rf_coordination.rf_channel import RFChannel
from micboard.multitenancy.models import Organization, OrganizationMembership
from micboard.services.core.performer_assignment import PerformerAssignmentService
from micboard.services.monitoring.alerts import acknowledge_alert, get_alerts_for_user
from micboard.services.monitoring.monitoring_access import MonitoringService


@override_settings(
    MICBOARD_ALLOW_CROSS_ORG_VIEW=False,
    MICBOARD_MSP_ENABLED=True,
    MICBOARD_MULTI_SITE_MODE=False,
)
class RestrictedSuperuserTenantAccessTests(TestCase):
    """Restricted superusers must remain inside their explicit tenant memberships."""

    def setUp(self) -> None:
        self.superuser = User.objects.create_superuser(
            username="restricted-superuser",
            password="test-pass",
        )
        alert_recipient = User.objects.create_user(username="tenant-alert-recipient")
        allowed_organization = Organization.objects.create(
            name="Allowed Tenant",
            slug="allowed-tenant",
        )
        denied_organization = Organization.objects.create(
            name="Denied Tenant",
            slug="denied-tenant",
        )
        OrganizationMembership.objects.create(
            user=self.superuser,
            organization=allowed_organization,
            role="operator",
        )

        self.allowed_building = Building.objects.create(
            name="Allowed Tenant Building",
            organization_id=allowed_organization.pk,
        )
        self.denied_building = Building.objects.create(
            name="Denied Tenant Building",
            organization_id=denied_organization.pk,
        )
        self.allowed_room = Room.objects.create(
            building=self.allowed_building,
            name="Allowed Tenant Room",
        )
        self.denied_room = Room.objects.create(
            building=self.denied_building,
            name="Denied Tenant Room",
        )
        allowed_location = Location.objects.create(
            building=self.allowed_building,
            room=self.allowed_room,
            name="Allowed Tenant Location",
        )
        denied_location = Location.objects.create(
            building=self.denied_building,
            room=self.denied_room,
            name="Denied Tenant Location",
        )

        self.allowed_group = MonitoringGroup.objects.create(name="Allowed Tenant Group")
        self.allowed_group.users.add(self.superuser)
        self.denied_group = MonitoringGroup.objects.create(name="Denied Tenant Group")
        self.denied_group.locations.add(denied_location)

        manufacturer = Manufacturer.objects.create(
            name="Restricted Tenant Manufacturer",
            code="restricted-tenant-manufacturer",
        )
        allowed_chassis = WirelessChassis.objects.create(
            manufacturer=manufacturer,
            api_device_id="restricted-allowed-chassis",
            role="receiver",
            ip="192.0.2.50",
            location=allowed_location,
        )
        denied_chassis = WirelessChassis.objects.create(
            manufacturer=manufacturer,
            api_device_id="restricted-denied-chassis",
            role="receiver",
            ip="192.0.2.51",
            location=denied_location,
        )
        self.allowed_channel, _ = RFChannel.objects.get_or_create(
            chassis=allowed_chassis,
            channel_number=1,
        )
        self.denied_channel, _ = RFChannel.objects.get_or_create(
            chassis=denied_chassis,
            channel_number=1,
        )

        self.allowed_alert = Alert.objects.create(
            channel=self.allowed_channel,
            user=alert_recipient,
            alert_type="signal_loss",
            status="pending",
            message="Allowed tenant alert",
        )
        self.denied_alert = Alert.objects.create(
            channel=self.denied_channel,
            user=alert_recipient,
            alert_type="signal_loss",
            status="pending",
            message="Denied tenant alert",
        )

        first_allowed_unit = WirelessUnit.objects.create(
            base_chassis=allowed_chassis,
            manufacturer=manufacturer,
            slot=1,
            name="Assigned Allowed Unit",
        )
        self.assignment_target = WirelessUnit.objects.create(
            base_chassis=allowed_chassis,
            manufacturer=manufacturer,
            slot=2,
            name="Assignment Target Unit",
        )
        self.performer = Performer.objects.create(name="Allowed Tenant Performer")
        PerformerAssignment.objects.create(
            performer=self.performer,
            wireless_unit=first_allowed_unit,
            monitoring_group=self.allowed_group,
        )

        self.client.force_login(self.superuser)

    def test_dashboard_routes_exclude_the_foreign_tenant(self) -> None:
        channel_ids = set(
            MonitoringService.get_accessible_channels(self.superuser).values_list(
                "pk",
                flat=True,
            )
        )
        self.assertIn(self.allowed_channel.pk, channel_ids)
        self.assertNotIn(self.denied_channel.pk, channel_ids)
        response = self.client.get(reverse("micboard:all_buildings_view"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.allowed_building.name)
        self.assertNotContains(response, self.denied_building.name)
        self.assertEqual(
            self.client.get(
                reverse("micboard:single_building_view", args=[self.denied_building.name])
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse(
                    "micboard:room_view",
                    args=[self.denied_building.name, self.denied_room.name],
                )
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                reverse("micboard:channel_card_partial", args=[self.allowed_channel.pk])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse("micboard:channel_card_partial", args=[self.denied_channel.pk])
            ).status_code,
            404,
        )

    def test_alert_reads_and_mutations_stay_inside_the_membership(self) -> None:
        self.assertEqual(
            set(get_alerts_for_user(self.superuser).values_list("pk", flat=True)),
            {self.allowed_alert.pk},
        )
        with self.assertRaises(Alert.DoesNotExist):
            acknowledge_alert(self.denied_alert.pk, user=self.superuser)

        self.assertEqual(
            self.client.get(
                reverse("micboard:alert_detail", args=[self.allowed_alert.pk])
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                reverse("micboard:alert_detail", args=[self.denied_alert.pk])
            ).status_code,
            404,
        )

        for route_name in ("micboard:acknowledge_alert", "micboard:resolve_alert"):
            with self.subTest(route_name=route_name):
                response = self.client.post(reverse(route_name, args=[self.denied_alert.pk]))
                self.assertEqual(response.status_code, 404)

        self.denied_alert.refresh_from_db()
        self.assertEqual(self.denied_alert.status, "pending")
        response = self.client.post(
            reverse("micboard:acknowledge_alert", args=[self.allowed_alert.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.allowed_alert.refresh_from_db()
        self.assertEqual(self.allowed_alert.status, "acknowledged")

    def test_assignment_form_and_write_exclude_the_foreign_group(self) -> None:
        form_response = self.client.get(reverse("micboard:create_assignment"))

        self.assertEqual(form_response.status_code, 200)
        self.assertContains(form_response, self.allowed_group.name)
        self.assertNotContains(form_response, self.denied_group.name)

        with self.assertRaises(PermissionDenied):
            PerformerAssignmentService.create_assignment(
                performer_id=self.performer.pk,
                unit_id=self.assignment_target.pk,
                group_id=self.denied_group.pk,
                user=self.superuser,
            )

        create_response = self.client.post(
            reverse("micboard:create_assignment"),
            {
                "performer_id": self.performer.pk,
                "wireless_unit_id": self.assignment_target.pk,
                "monitoring_group_id": self.denied_group.pk,
            },
        )

        self.assertEqual(create_response.status_code, 403)
        self.assertFalse(
            PerformerAssignment.objects.filter(
                performer=self.performer,
                wireless_unit=self.assignment_target,
            ).exists()
        )
