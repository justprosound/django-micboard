"""Request-level discovery approval smoke coverage."""

from django.test import Client
from django.urls import reverse

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.queue import DiscoveryQueue
from micboard.models.hardware.wireless_chassis import WirelessChassis
from tests.admin.helpers import grant_permissions
from tests.factories.base import UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


def test_discovery_approval_enforces_permissions_and_is_idempotent() -> None:
    """The HTTP action must deny unrelated staff and import a queue item once."""
    manufacturer = Manufacturer.objects.create(
        name="Approval Manufacturer",
        code="approval-manufacturer",
    )
    queue_item = DiscoveryQueue.objects.create(
        manufacturer=manufacturer,
        api_device_id="approval-device",
        serial_number="APPROVAL-SERIAL",
        ip="192.0.2.20",
        name="Approval Device",
        device_type="receiver",
    )
    unauthorized = UserFactory(username="discovery-reviewer", is_staff=True)
    authorized = UserFactory(username="inventory-reviewer", is_staff=True)
    queue_permissions = ("view_discoveryqueue", "change_discoveryqueue")
    grant_permissions(unauthorized, *queue_permissions)
    grant_permissions(
        authorized,
        *queue_permissions,
        "add_wirelesschassis",
        "change_wirelesschassis",
    )
    action_url = reverse("admin:micboard_discoveryqueue_changelist")
    action_data = {"action": "approve_devices", "_selected_action": queue_item.pk, "index": "0"}
    client = Client()
    client.force_login(unauthorized)

    denied_response = client.post(action_url, action_data)

    assert denied_response.status_code == 403
    queue_item.refresh_from_db()
    assert queue_item.status == "pending"
    assert not WirelessChassis.objects.filter(api_device_id="approval-device").exists()

    client.force_login(authorized)
    approved_response = client.post(action_url, action_data)

    assert approved_response.status_code == 302
    queue_item.refresh_from_db()
    first_reviewed_at = queue_item.reviewed_at
    assert queue_item.status == "imported"
    assert queue_item.reviewed_by == authorized
    assert first_reviewed_at is not None
    assert (
        WirelessChassis.objects.filter(
            manufacturer=manufacturer,
            api_device_id="approval-device",
            serial_number="APPROVAL-SERIAL",
        ).count()
        == 1
    )

    replay_response = client.post(action_url, action_data)

    assert replay_response.status_code == 302
    queue_item.refresh_from_db()
    assert queue_item.reviewed_at == first_reviewed_at
    assert (
        WirelessChassis.objects.filter(
            manufacturer=manufacturer,
            api_device_id="approval-device",
        ).count()
        == 1
    )
