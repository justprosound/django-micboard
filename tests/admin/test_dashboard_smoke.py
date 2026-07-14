"""Request-level monitoring dashboard smoke coverage."""

from django.test import Client, override_settings
from django.urls import reverse

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.monitoring.group import MonitoringGroup
from tests.admin.helpers import create_chassis, create_location
from tests.factories.base import UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


def test_monitoring_dashboard_counts_only_accessible_inventory() -> None:
    """Dashboard summary counts must match the user's monitoring scope."""
    user = UserFactory(username="dashboard-operator")
    foreign_user = UserFactory(username="foreign-dashboard-operator")
    allowed_location = create_location(name="Dashboard Allowed")
    foreign_location = create_location(name="Dashboard Foreign")
    manufacturer = Manufacturer.objects.create(
        name="Dashboard Manufacturer",
        code="dashboard-smoke-manufacturer",
    )
    create_chassis(
        name="Dashboard Allowed Chassis",
        manufacturer=manufacturer,
        location=allowed_location,
        ip="192.0.2.30",
    )
    create_chassis(
        name="Dashboard Foreign Chassis",
        manufacturer=manufacturer,
        location=foreign_location,
        ip="192.0.2.31",
    )
    allowed_group = MonitoringGroup.objects.create(name="Dashboard Allowed Group")
    allowed_group.users.add(user)
    allowed_group.locations.add(allowed_location)
    foreign_group = MonitoringGroup.objects.create(name="Dashboard Foreign Group")
    foreign_group.users.add(foreign_user)
    foreign_group.locations.add(foreign_location)
    client = Client()
    client.force_login(user)

    with override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=False):
        response = client.get(reverse("micboard:index"))

    assert response.status_code == 200
    assert (response.context["device_count"], response.context["group_count"]) == (1, 1)
    assert 'aria-label="Monitoring summary"' in response.content.decode()
