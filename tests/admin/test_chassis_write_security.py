"""Request-level tenant security regressions for chassis admin writes."""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth.models import User
from django.test import Client, override_settings
from django.urls import reverse

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.locations.structure import Location
from micboard.multitenancy.models import Organization
from tests.admin.helpers import create_location, grant_permissions
from tests.factories.multitenancy import OrganizationFactory, OrganizationMembershipFactory

pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


@dataclass(frozen=True)
class ChassisAdminWriteGraph:
    """Tenant administrator and locations used by admin write regressions."""

    client: Client
    user: User
    manufacturer: Manufacturer
    allowed_location: Location
    foreign_location: Location


@pytest.fixture
def chassis_admin_write_graph() -> ChassisAdminWriteGraph:
    """Create one manageable location and one foreign isolation control."""
    user = User.objects.create_user(username="chassis-write-admin", is_staff=True)
    grant_permissions(
        user,
        "view_wirelesschassis",
        "add_wirelesschassis",
        "change_wirelesschassis",
    )
    allowed_organization = OrganizationFactory(max_devices=5)
    foreign_organization = OrganizationFactory(max_devices=5)
    OrganizationMembershipFactory(
        user=user,
        organization=allowed_organization,
        campus=None,
        role="admin",
    )
    allowed_location = create_location(
        name="Managed chassis location",
        organization=allowed_organization,
    )
    foreign_location = create_location(
        name="Foreign chassis location",
        organization=foreign_organization,
    )
    manufacturer = Manufacturer.objects.create(
        name="Chassis write manufacturer",
        code="chassis-write-manufacturer",
    )
    client = Client()
    client.force_login(user)
    return ChassisAdminWriteGraph(
        client=client,
        user=user,
        manufacturer=manufacturer,
        allowed_location=allowed_location,
        foreign_location=foreign_location,
    )


def _chassis_post_data(
    graph: ChassisAdminWriteGraph,
    *,
    identity: str,
    ip: str,
    location: Location | str | None,
) -> dict[str, str | int]:
    """Build the complete editable chassis payload expected by Django admin."""
    location_value = location.pk if isinstance(location, Location) else location or ""
    return {
        "role": "receiver",
        "manufacturer": graph.manufacturer.pk,
        "api_device_id": identity,
        "name": identity,
        "ip": ip,
        "network_mode": "auto",
        "status": "discovered",
        "location": location_value,
        "order": 0,
        "max_channels": 0,
        "protocol_family": "legacy_uhf",
        "licensed_resource_count": 0,
        "_save": "Save",
    }


def _location_errors(response) -> list[str]:
    """Return rendered location errors from an invalid admin change form."""
    return list(response.context["adminform"].form.errors.get("location", ()))


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_tenant_admin_add_requires_managed_location(
    chassis_admin_write_graph: ChassisAdminWriteGraph,
) -> None:
    """A tenant administrator cannot convert an add into platform inventory."""
    response = chassis_admin_write_graph.client.post(
        reverse("admin:micboard_wirelesschassis_add"),
        _chassis_post_data(
            chassis_admin_write_graph,
            identity="blank-location-device",
            ip="192.0.2.91",
            location=None,
        ),
    )

    assert response.status_code == 200
    assert _location_errors(response) == [
        "A managed location is required for tenant administrators."
    ]
    assert not WirelessChassis.objects.filter(api_device_id="blank-location-device").exists()


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_tenant_admin_add_rejects_forged_foreign_location(
    chassis_admin_write_graph: ChassisAdminWriteGraph,
) -> None:
    """A forged location primary key cannot cross the organization boundary."""
    response = chassis_admin_write_graph.client.post(
        reverse("admin:micboard_wirelesschassis_add"),
        _chassis_post_data(
            chassis_admin_write_graph,
            identity="foreign-location-device",
            ip="192.0.2.92",
            location=chassis_admin_write_graph.foreign_location,
        ),
    )

    assert response.status_code == 200
    assert _location_errors(response)
    assert not WirelessChassis.objects.filter(api_device_id="foreign-location-device").exists()


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_tenant_admin_change_cannot_clear_ownership_location(
    chassis_admin_write_graph: ChassisAdminWriteGraph,
) -> None:
    """Clearing an existing location cannot turn tenant inventory into platform inventory."""
    chassis = WirelessChassis.objects.create(
        role="receiver",
        manufacturer=chassis_admin_write_graph.manufacturer,
        api_device_id="owned-device",
        name="Owned device",
        ip="192.0.2.93",
        location=chassis_admin_write_graph.allowed_location,
        max_channels=0,
    )
    response = chassis_admin_write_graph.client.post(
        reverse("admin:micboard_wirelesschassis_change", args=[chassis.pk]),
        _chassis_post_data(
            chassis_admin_write_graph,
            identity=chassis.api_device_id,
            ip=str(chassis.ip),
            location=None,
        ),
    )

    assert response.status_code == 200
    assert _location_errors(response) == [
        "A managed location is required for tenant administrators."
    ]
    chassis.refresh_from_db()
    assert chassis.location == chassis_admin_write_graph.allowed_location


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_tenant_admin_add_uses_organization_quota(
    chassis_admin_write_graph: ChassisAdminWriteGraph,
) -> None:
    """Admin adds use the canonical quota boundary instead of raw model save."""
    organization = Organization.objects.get(
        pk=chassis_admin_write_graph.allowed_location.building.organization_id
    )
    organization.max_devices = 1
    organization.save(update_fields=["max_devices"])
    WirelessChassis.objects.create(
        role="receiver",
        manufacturer=chassis_admin_write_graph.manufacturer,
        api_device_id="quota-existing-device",
        ip="192.0.2.94",
        location=chassis_admin_write_graph.allowed_location,
        max_channels=0,
    )

    response = chassis_admin_write_graph.client.post(
        reverse("admin:micboard_wirelesschassis_add"),
        _chassis_post_data(
            chassis_admin_write_graph,
            identity="quota-overflow-device",
            ip="192.0.2.95",
            location=chassis_admin_write_graph.allowed_location,
        ),
    )

    assert response.status_code == 200
    assert "has reached its device quota" in " ".join(_location_errors(response))
    assert not WirelessChassis.objects.filter(api_device_id="quota-overflow-device").exists()


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_tenant_admin_add_persists_owned_chassis(
    chassis_admin_write_graph: ChassisAdminWriteGraph,
) -> None:
    """A valid tenant-owned admin add still succeeds through the service seam."""
    response = chassis_admin_write_graph.client.post(
        reverse("admin:micboard_wirelesschassis_add"),
        _chassis_post_data(
            chassis_admin_write_graph,
            identity="managed-location-device",
            ip="192.0.2.96",
            location=chassis_admin_write_graph.allowed_location,
        ),
    )

    assert response.status_code == 302
    created = WirelessChassis.objects.get(api_device_id="managed-location-device")
    assert created.location == chassis_admin_write_graph.allowed_location
