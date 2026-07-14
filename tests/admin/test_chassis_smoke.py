"""Request-level chassis admin smoke coverage."""

from django.test import Client, override_settings
from django.urls import reverse

import pytest

from tests.admin.helpers import create_tenant_inventory, grant_permissions
from tests.factories.base import UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


def test_chassis_changelist_is_tenant_scoped() -> None:
    """The rendered admin changelist must not reveal foreign tenant hardware."""
    staff_user = UserFactory(username="chassis-admin", is_staff=True)
    grant_permissions(staff_user, "view_wirelesschassis")
    inventory = create_tenant_inventory(staff_user)
    client = Client()
    client.force_login(staff_user)

    with override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False):
        response = client.get(reverse("admin:micboard_wirelesschassis_changelist"))

    assert response.status_code == 200
    assert {item.pk for item in response.context["cl"].result_list} == {
        inventory.allowed_chassis.pk
    }
    assert "Allowed Chassis" in response.content.decode()
    assert "Foreign Chassis" not in response.content.decode()
