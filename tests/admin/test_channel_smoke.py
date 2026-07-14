"""Request-level HTMX channel fragment smoke coverage."""

from django.test import Client
from django.urls import reverse

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.monitoring.group import MonitoringGroup
from tests.admin.helpers import create_chassis, create_location
from tests.factories.base import UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


def test_htmx_channel_fragment_hides_foreign_channels() -> None:
    """The channel fragment must render allowed unit data and 404 foreign IDs."""
    user = UserFactory(username="fragment-operator")
    foreign_user = UserFactory(username="foreign-fragment-operator")
    allowed_location = create_location(name="Fragment Allowed")
    foreign_location = create_location(name="Fragment Foreign")
    manufacturer = Manufacturer.objects.create(
        name="Fragment Manufacturer",
        code="fragment-manufacturer",
    )
    allowed_chassis = create_chassis(
        name="Fragment Allowed Chassis",
        manufacturer=manufacturer,
        location=allowed_location,
        ip="192.0.2.40",
        max_channels=1,
    )
    foreign_chassis = create_chassis(
        name="Fragment Foreign Chassis",
        manufacturer=manufacturer,
        location=foreign_location,
        ip="192.0.2.41",
        max_channels=1,
    )
    allowed_group = MonitoringGroup.objects.create(name="Fragment Allowed Group")
    allowed_group.users.add(user)
    allowed_group.locations.add(allowed_location)
    foreign_group = MonitoringGroup.objects.create(name="Fragment Foreign Group")
    foreign_group.users.add(foreign_user)
    foreign_group.locations.add(foreign_location)
    allowed_channel = allowed_chassis.rf_channels.get(channel_number=1)
    foreign_channel = foreign_chassis.rf_channels.get(channel_number=1)
    unit = WirelessUnit.objects.create(
        base_chassis=allowed_chassis,
        manufacturer=manufacturer,
        serial_number="FRAGMENT-UNIT",
        name="Lead Vocal Unit",
        slot=1,
        battery=204,
    )
    allowed_channel.active_wireless_unit = unit
    allowed_channel.resource_state = "active"
    allowed_channel.rf_signal_strength = -55
    allowed_channel.audio_level = -12
    allowed_channel.save(
        update_fields={
            "active_wireless_unit",
            "resource_state",
            "rf_signal_strength",
            "audio_level",
        }
    )
    client = Client()
    client.force_login(user)

    allowed_response = client.get(
        reverse("micboard:channel_card_partial", args=[allowed_channel.pk]),
        headers={"HX-Request": "true"},
    )
    foreign_response = client.get(
        reverse("micboard:channel_card_partial", args=[foreign_channel.pk]),
        headers={"HX-Request": "true"},
    )

    assert allowed_response.status_code == 200
    assert f'id="channel-{allowed_channel.pk}"' in allowed_response.content.decode()
    assert "Lead Vocal Unit" in allowed_response.content.decode()
    assert "80%" in allowed_response.content.decode()
    assert foreign_response.status_code == 404
