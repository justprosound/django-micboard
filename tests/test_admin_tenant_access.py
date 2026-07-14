"""Tenant-isolation regression tests for shared Micboard admin behavior."""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission, User
from django.test import RequestFactory, override_settings

import pytest

from micboard.admin.display_wall import WallSectionAdmin
from micboard.admin.manufacturers import ManufacturerAdmin
from micboard.admin.receivers import WirelessChassisAdmin
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.charger import Charger
from micboard.models.hardware.display_wall import WallSection
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.locations.structure import Building, Location
from micboard.multitenancy.models import Campus, Organization, OrganizationMembership


@dataclass(frozen=True)
class TenantAdminGraph:
    """Objects spanning an allowed campus and two denied tenant scopes."""

    staff_user: User
    allowed_location: Location
    denied_campus_location: Location
    denied_organization_location: Location
    allowed_chassis: WirelessChassis
    denied_campus_chassis: WirelessChassis
    denied_organization_chassis: WirelessChassis
    allowed_charger: Charger
    denied_campus_charger: Charger
    denied_organization_charger: Charger


def _request_for(user: User):
    """Build an admin request for a concrete user."""
    request = RequestFactory().get("/admin/micboard/wirelesschassis/")
    request.user = user
    return request


def _create_location(
    *,
    name: str,
    organization: Organization,
    campus: Campus,
) -> Location:
    building = Building.objects.create(
        name=f"{name} Building",
        organization_id=organization.pk,
        campus_id=campus.pk,
    )
    return Location.objects.create(building=building, name=name)


@pytest.fixture
def tenant_admin_graph(db) -> TenantAdminGraph:
    """Create one allowed scope plus campus and organization isolation controls."""
    staff_user = User.objects.create_user(
        username="tenant-admin",
        is_staff=True,
    )
    staff_user.user_permissions.add(
        Permission.objects.get(codename="view_wirelesschassis"),
        Permission.objects.get(codename="change_wirelesschassis"),
    )

    allowed_organization = Organization.objects.create(
        name="Allowed Organization",
        slug="allowed-organization",
    )
    denied_organization = Organization.objects.create(
        name="Denied Organization",
        slug="denied-organization",
    )
    allowed_campus = Campus.objects.create(
        organization=allowed_organization,
        name="Allowed Campus",
        slug="allowed-campus",
    )
    denied_campus = Campus.objects.create(
        organization=allowed_organization,
        name="Denied Campus",
        slug="denied-campus",
    )
    denied_organization_campus = Campus.objects.create(
        organization=denied_organization,
        name="Other Campus",
        slug="other-campus",
    )
    OrganizationMembership.objects.create(
        user=staff_user,
        organization=allowed_organization,
        campus=allowed_campus,
        role="admin",
    )
    OrganizationMembership.objects.create(
        user=staff_user,
        organization=denied_organization,
        campus=denied_organization_campus,
        role="admin",
        is_active=False,
    )

    allowed_location = _create_location(
        name="Allowed Location",
        organization=allowed_organization,
        campus=allowed_campus,
    )
    denied_campus_location = _create_location(
        name="Denied Campus Location",
        organization=allowed_organization,
        campus=denied_campus,
    )
    denied_organization_location = _create_location(
        name="Denied Organization Location",
        organization=denied_organization,
        campus=denied_organization_campus,
    )

    manufacturer = Manufacturer.objects.create(
        name="Tenant Admin Manufacturer",
        code="tenant-admin-manufacturer",
    )

    def create_chassis(name: str, location: Location, ip: str) -> WirelessChassis:
        return WirelessChassis.objects.create(
            name=name,
            manufacturer=manufacturer,
            api_device_id=name.lower().replace(" ", "-"),
            role="receiver",
            location=location,
            ip=ip,
        )

    def create_charger(name: str, location: Location) -> Charger:
        return Charger.objects.create(
            name=name,
            location=location,
        )

    return TenantAdminGraph(
        staff_user=staff_user,
        allowed_location=allowed_location,
        denied_campus_location=denied_campus_location,
        denied_organization_location=denied_organization_location,
        allowed_chassis=create_chassis("Allowed Chassis", allowed_location, "192.0.2.10"),
        denied_campus_chassis=create_chassis(
            "Denied Campus Chassis",
            denied_campus_location,
            "192.0.2.11",
        ),
        denied_organization_chassis=create_chassis(
            "Denied Organization Chassis",
            denied_organization_location,
            "192.0.2.12",
        ),
        allowed_charger=create_charger("Allowed Charger", allowed_location),
        denied_campus_charger=create_charger("Denied Campus Charger", denied_campus_location),
        denied_organization_charger=create_charger(
            "Denied Organization Charger",
            denied_organization_location,
        ),
    )


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_admin_queryset_honors_active_organization_and_campus_memberships(
    tenant_admin_graph: TenantAdminGraph,
) -> None:
    """Model permission must not expand changelist access beyond tenant memberships."""
    model_admin = WirelessChassisAdmin(WirelessChassis, AdminSite())

    visible_ids = set(
        model_admin.get_queryset(_request_for(tenant_admin_graph.staff_user)).values_list(
            "pk",
            flat=True,
        )
    )

    assert visible_ids == {tenant_admin_graph.allowed_chassis.pk}


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=True)
def test_admin_superuser_cross_organization_setting_matches_manager_contract(
    tenant_admin_graph: TenantAdminGraph,
) -> None:
    """Cross-organization superusers retain the manager contract's global view."""
    superuser = User.objects.create_superuser(username="cross-org-admin")
    model_admin = WirelessChassisAdmin(WirelessChassis, AdminSite())

    visible_ids = set(
        model_admin.get_queryset(_request_for(superuser)).values_list("pk", flat=True)
    )

    assert visible_ids == {
        tenant_admin_graph.allowed_chassis.pk,
        tenant_admin_graph.denied_campus_chassis.pk,
        tenant_admin_graph.denied_organization_chassis.pk,
    }


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_admin_superuser_without_cross_organization_view_requires_membership(
    tenant_admin_graph: TenantAdminGraph,
) -> None:
    """A restricted superuser receives no implicit cross-tenant bypass."""
    superuser = User.objects.create_superuser(username="restricted-admin")
    model_admin = WirelessChassisAdmin(WirelessChassis, AdminSite())

    assert not model_admin.get_queryset(_request_for(superuser)).exists()


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=False)
def test_admin_queryset_preserves_non_msp_behavior(
    tenant_admin_graph: TenantAdminGraph,
) -> None:
    """Tenant filtering remains inactive for ordinary single-tenant hosts."""
    model_admin = WirelessChassisAdmin(WirelessChassis, AdminSite())

    visible_ids = set(
        model_admin.get_queryset(_request_for(tenant_admin_graph.staff_user)).values_list(
            "pk",
            flat=True,
        )
    )

    assert visible_ids == {
        tenant_admin_graph.allowed_chassis.pk,
        tenant_admin_graph.denied_campus_chassis.pk,
        tenant_admin_graph.denied_organization_chassis.pk,
    }


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_admin_foreign_key_choices_are_tenant_scoped(
    tenant_admin_graph: TenantAdminGraph,
) -> None:
    """Foreign-key widgets must not expose locations outside active memberships."""
    model_admin = WirelessChassisAdmin(WirelessChassis, AdminSite())

    formfield = model_admin.formfield_for_foreignkey(
        WirelessChassis._meta.get_field("location"),
        _request_for(tenant_admin_graph.staff_user),
    )

    assert set(formfield.queryset.values_list("pk", flat=True)) == {
        tenant_admin_graph.allowed_location.pk,
    }


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_admin_many_to_many_choices_are_tenant_scoped(
    tenant_admin_graph: TenantAdminGraph,
) -> None:
    """Many-to-many widgets must not expose targets outside active memberships."""
    model_admin = WallSectionAdmin(WallSection, AdminSite())

    formfield = model_admin.formfield_for_manytomany(
        WallSection._meta.get_field("chargers"),
        _request_for(tenant_admin_graph.staff_user),
    )

    assert set(formfield.queryset.values_list("pk", flat=True)) == {
        tenant_admin_graph.allowed_charger.pk,
    }


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_unscoped_admin_model_fails_closed(tenant_admin_graph: TenantAdminGraph) -> None:
    """Models without a safe tenant lookup cannot leak through admin in MSP mode."""
    model_admin = ManufacturerAdmin(Manufacturer, admin.site)

    assert not model_admin.get_queryset(_request_for(tenant_admin_graph.staff_user)).exists()


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_unscoped_admin_custom_view_fails_closed(
    tenant_admin_graph: TenantAdminGraph,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custom admin URLs must apply the same tenant boundary as changelists."""
    tenant_admin_graph.staff_user.user_permissions.add(
        Permission.objects.get(codename="view_manufacturer")
    )
    manufacturer = Manufacturer.objects.get(code="tenant-admin-manufacturer")
    model_admin = ManufacturerAdmin(Manufacturer, admin.site)
    monkeypatch.setattr(model_admin, "message_user", lambda *args, **kwargs: None)

    response = model_admin.discovery_ips_view(
        _request_for(tenant_admin_graph.staff_user),
        manufacturer.pk,
    )

    assert response.status_code == 302
