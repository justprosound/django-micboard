"""Tests for the v1 Read-Only REST API.

Uses pytest-django conventions (``@pytest.mark.django_db``, fixtures, plain
``assert`` statements) instead of Django's ``unittest.TestCase`` hierarchy so
the test integrates cleanly with the rest of the suite.
"""

from __future__ import annotations

from django.urls import reverse

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.registry import DiscoveredDevice
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.locations.structure import Building, Location
from micboard.models.monitoring.alert import Alert
from micboard.models.monitoring.group import MonitoringGroup
from micboard.models.settings.registry import Setting, SettingDefinition

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def api_client() -> APIClient:
    """Provide a DRF API client."""
    return APIClient()


@pytest.fixture()
def superuser(db, django_user_model):
    """Create a superuser for API tests."""
    return django_user_model.objects.create_superuser(
        username="api-superuser",
        password="test-password",
    )


@pytest.fixture()
def regular_user(db, django_user_model):
    """Create a regular user for API tests."""
    return django_user_model.objects.create_user(
        username="api-user",
        password="test-password",
    )


@pytest.fixture()
def _api_seed(db, superuser, regular_user):
    """Seed the database with test data for v1 API tests.

    Returns a namespace-dict so individual tests can reference created objects
    without coupling to the fixture's internals.
    """
    # Locations
    building = Building.objects.create(name="Test Building")
    location = Location.objects.create(building=building, name="Test Location")

    # Monitoring group scoped to regular_user + location
    group = MonitoringGroup.objects.create(name="Test Group")
    group.users.add(regular_user)
    group.locations.add(location)

    # Manufacturer & hardware
    manufacturer = Manufacturer.objects.create(name="Test Brand", code="test-brand")
    chassis = WirelessChassis.objects.create(
        manufacturer=manufacturer,
        api_device_id="chassis-1",
        role="receiver",
        ip="192.0.2.1",
        location=location,
    )
    WirelessUnit.objects.create(
        base_chassis=chassis,
        manufacturer=manufacturer,
        slot=1,
        name="Unit 1",
    )
    channel = chassis.rf_channels.get(channel_number=1)

    # Alerts — one per user
    alert_for_user = Alert.objects.create(
        channel=channel,
        user=regular_user,
        alert_type="signal_loss",
        status="pending",
        message="Test alert message",
        channel_data={"secret_token": "super-secret-token", "rf_level": -85},
    )
    Alert.objects.create(
        channel=channel,
        user=superuser,
        alert_type="signal_loss",
        status="pending",
        message="Superuser alert message",
        channel_data={"rf_level": -90},
    )

    # Discovered devices
    DiscoveredDevice.objects.create(
        ip="192.0.2.100",
        device_type="receiver",
        manufacturer=manufacturer,
        metadata={"admin_password": "supersecretpassword", "firmware": "1.0"},
    )

    # Settings — one sensitive, one normal
    sensitive_defn = SettingDefinition.objects.create(
        key="api_secret_key",
        label="API Secret Key",
        scope=SettingDefinition.SCOPE_GLOBAL,
        setting_type=SettingDefinition.TYPE_STRING,
        default_value="defaultsecretvalue",
    )
    Setting.objects.create(definition=sensitive_defn, value="overriddensecretvalue")

    normal_defn = SettingDefinition.objects.create(
        key="normal_setting",
        label="Normal Setting",
        scope=SettingDefinition.SCOPE_GLOBAL,
        setting_type=SettingDefinition.TYPE_INTEGER,
        default_value="10",
    )
    Setting.objects.create(definition=normal_defn, value="20")

    return {
        "chassis": chassis,
        "alert_for_user": alert_for_user,
        "sensitive_defn": sensitive_defn,
        "normal_defn": normal_defn,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestV1AnonymousAccess:
    """Anonymous requests must return 401 for every endpoint."""

    def test_anonymous_access_denied(self, api_client, _api_seed) -> None:
        chassis = _api_seed["chassis"]
        urls = [
            reverse("micboard:api_v1:chassis-list"),
            reverse("micboard:api_v1:chassis-detail", args=[chassis.pk]),
            reverse("micboard:api_v1:units-list"),
            reverse("micboard:api_v1:channels-list"),
            reverse("micboard:api_v1:discovery-list"),
            reverse("micboard:api_v1:monitoring-group-list"),
            reverse("micboard:api_v1:alert-list"),
            reverse("micboard:api_v1:settingdefinition-list"),
            reverse("micboard:api_v1:setting-list"),
        ]
        denied = {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}
        for url in urls:
            response = api_client.get(url)
            assert response.status_code in denied, (
                f"{url} returned {response.status_code}, expected 401 or 403"
            )


@pytest.mark.django_db
class TestV1ReadOnlyEnforcement:
    """Only GET/HEAD/OPTIONS are permitted; mutating methods return 405."""

    def test_post_not_allowed(self, api_client, superuser, _api_seed) -> None:
        api_client.force_authenticate(user=superuser)
        url = reverse("micboard:api_v1:chassis-list")
        response = api_client.post(url, {"name": "New Chassis"})
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


def test_put_patch_delete_not_allowed(api_client, superuser, _api_seed) -> None:
    api_client.force_authenticate(user=superuser)
    chassis = _api_seed["chassis"]
    detail_url = reverse("micboard:api_v1:chassis-detail", args=[chassis.pk])

    put_response = api_client.put(detail_url, {})
    patch_response = api_client.patch(detail_url, {})
    delete_response = api_client.delete(detail_url)

    assert put_response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    assert patch_response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
    assert delete_response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.django_db
class TestV1SuperuserScoping:
    """Superusers see all records across all endpoints."""

    def test_superuser_sees_all_chassis(self, api_client, superuser, _api_seed) -> None:
        api_client.force_authenticate(user=superuser)
        response = api_client.get(reverse("micboard:api_v1:chassis-list"))
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_superuser_sees_all_discovery(self, api_client, superuser, _api_seed) -> None:
        api_client.force_authenticate(user=superuser)
        response = api_client.get(reverse("micboard:api_v1:discovery-list"))
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_superuser_sees_all_alerts(self, api_client, superuser, _api_seed) -> None:
        api_client.force_authenticate(user=superuser)
        response = api_client.get(reverse("micboard:api_v1:alert-list"))
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 2


@pytest.mark.django_db
class TestV1RegularUserScoping:
    """Regular users see only records scoped to their monitoring groups."""

    def test_regular_user_sees_scoped_chassis(self, api_client, regular_user, _api_seed) -> None:
        api_client.force_authenticate(user=regular_user)
        response = api_client.get(reverse("micboard:api_v1:chassis-list"))
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_regular_user_cannot_see_discovery(self, api_client, regular_user, _api_seed) -> None:
        api_client.force_authenticate(user=regular_user)
        response = api_client.get(reverse("micboard:api_v1:discovery-list"))
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 0

    def test_regular_user_sees_own_alerts_only(self, api_client, regular_user, _api_seed) -> None:
        api_client.force_authenticate(user=regular_user)
        alert_for_user = _api_seed["alert_for_user"]
        response = api_client.get(reverse("micboard:api_v1:alert-list"))
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["message"] == alert_for_user.message


@pytest.mark.django_db
class TestV1RedactionRules:
    """Sensitive data is redacted in API responses."""

    def test_setting_definition_redacts_sensitive_default(
        self, api_client, superuser, _api_seed
    ) -> None:
        api_client.force_authenticate(user=superuser)
        response = api_client.get(reverse("micboard:api_v1:settingdefinition-list"))
        assert response.status_code == status.HTTP_200_OK

        sensitive = next(d for d in response.data if d["key"] == "api_secret_key")
        normal = next(d for d in response.data if d["key"] == "normal_setting")
        assert sensitive["default_value"] == "********"
        assert normal["default_value"] == "10"

    def test_setting_redacts_sensitive_value(self, api_client, superuser, _api_seed) -> None:
        api_client.force_authenticate(user=superuser)
        sensitive_defn = _api_seed["sensitive_defn"]
        normal_defn = _api_seed["normal_defn"]

        response = api_client.get(reverse("micboard:api_v1:setting-list"))
        assert response.status_code == status.HTTP_200_OK

        sensitive = next(s for s in response.data if s["definition"] == sensitive_defn.pk)
        normal = next(s for s in response.data if s["definition"] == normal_defn.pk)
        assert sensitive["value"] == "********"
        assert normal["value"] == "20"

    def test_discovery_metadata_redacted(self, api_client, superuser, _api_seed) -> None:
        api_client.force_authenticate(user=superuser)
        response = api_client.get(reverse("micboard:api_v1:discovery-list"))
        assert response.status_code == status.HTTP_200_OK

        dev = response.data[0]
        assert dev["metadata"]["admin_password"] == "********"
        assert dev["metadata"]["firmware"] == "1.0"

    def test_alert_channel_data_redacted(self, api_client, superuser, _api_seed) -> None:
        api_client.force_authenticate(user=superuser)
        alert_for_user = _api_seed["alert_for_user"]

        response = api_client.get(reverse("micboard:api_v1:alert-list"))
        assert response.status_code == status.HTTP_200_OK

        alert = next(a for a in response.data if a["id"] == alert_for_user.pk)
        assert alert["channel_data"]["secret_token"] == "********"
        assert alert["channel_data"]["rf_level"] == -85
