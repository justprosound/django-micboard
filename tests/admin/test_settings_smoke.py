"""Request-level settings administration smoke coverage."""

from django.test import Client, override_settings
from django.urls import reverse

import pytest

from micboard.models.settings.registry import Setting, SettingDefinition
from tests.admin.helpers import create_tenant_inventory, grant_permissions
from tests.factories.base import UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


def test_settings_diff_is_tenant_scoped_and_redacts_secrets() -> None:
    """Settings diff must show allowed scopes without exposing stored secrets."""
    staff_user = UserFactory(username="settings-admin", is_staff=True)
    grant_permissions(staff_user, "view_setting")
    inventory = create_tenant_inventory(staff_user)
    staff_user.org_memberships.update(campus=None)
    definition = SettingDefinition.objects.create(
        key="API_SECRET_TOKEN",
        label="API Secret Token",
        setting_type=SettingDefinition.TYPE_STRING,
        default_value="default-secret",
    )
    scoped_values = {
        "global-secret-value": {},
        "allowed-organization-secret": {
            "organization_id": inventory.allowed_organization.pk,
        },
        "foreign-organization-secret": {
            "organization_id": inventory.foreign_organization.pk,
        },
        "allowed-site-secret": {"site": inventory.allowed_site},
        "foreign-site-secret": {"site": inventory.foreign_site},
        "allowed-manufacturer-secret": {
            "manufacturer_id": inventory.allowed_manufacturer.pk,
        },
        "foreign-manufacturer-secret": {
            "manufacturer_id": inventory.foreign_manufacturer.pk,
        },
    }
    for value, scope in scoped_values.items():
        Setting.objects.create(definition=definition, value=value, **scope)

    client = Client()
    client.force_login(staff_user)
    with override_settings(
        MICBOARD_MSP_ENABLED=True,
        MICBOARD_MULTI_SITE_MODE=True,
        MICBOARD_ALLOW_CROSS_ORG_VIEW=False,
        SITE_ID=inventory.allowed_site.pk,
    ):
        response = client.get(reverse("micboard:settings_diff"))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Allowed Organization" in content
    assert "Foreign Organization" not in content
    assert "Allowed Site" not in content
    assert "Foreign Site" not in content
    assert "Allowed Manufacturer" not in content
    assert "Foreign Manufacturer" not in content
    assert "••••••" in content
    for raw_value in scoped_values:
        assert raw_value not in content
