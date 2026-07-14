"""Tenant-isolation regression tests for shared Micboard admin behavior."""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission, User
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.test import RequestFactory, override_settings

import pytest

from micboard.admin.display_wall import WallSectionAdmin, WallSectionInline
from micboard.admin.manufacturers import ManufacturerAdmin
from micboard.admin.mixins import PLATFORM_GLOBAL_ADMIN_MODEL_LABELS
from micboard.admin.realtime import RealTimeConnectionAdmin
from micboard.admin.receivers import RFChannelInline, WirelessChassisAdmin
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.charger import Charger
from micboard.models.hardware.display_wall import DisplayWall, WallSection
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.locations.structure import Building, Location
from micboard.models.monitoring.group import MonitoringGroup, MonitoringGroupLocation
from micboard.models.realtime.connection import RealTimeConnection
from micboard.multitenancy.admin import SuperuserOnlyAdmin
from micboard.multitenancy.models import Campus, Organization, OrganizationMembership
from tests.factories.hardware import WirelessChassisFactory, WirelessUnitFactory


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


def test_platform_global_admin_allowlist_excludes_nested_tenant_models() -> None:
    """Only reviewed host-wide records may bypass site scoping for superusers."""
    assert {
        "micboard.activitylog",
        "micboard.discovereddevice",
        "micboard.discoverycidr",
        "micboard.discoveryfqdn",
        "micboard.discoveryjob",
        "micboard.discoveryqueue",
        "micboard.servicesynclog",
        "micboard.useralertpreference",
    } <= PLATFORM_GLOBAL_ADMIN_MODEL_LABELS
    assert {
        "micboard.alert",
        "micboard.chargerslot",
        "micboard.devicemovementlog",
        "micboard.wallsection",
    }.isdisjoint(PLATFORM_GLOBAL_ADMIN_MODEL_LABELS)


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
def test_admin_form_keeps_shared_manufacturers_and_scopes_locations(
    tenant_admin_graph: TenantAdminGraph,
) -> None:
    """Global catalogs stay usable without exposing tenant-owned locations."""
    second_manufacturer = Manufacturer.objects.create(
        name="Second Shared Manufacturer",
        code="second-shared-manufacturer",
    )
    model_admin = WirelessChassisAdmin(WirelessChassis, AdminSite())
    request = _request_for(tenant_admin_graph.staff_user)

    form = model_admin.get_form(request)()
    rendered_form = form.as_p()

    assert set(form.fields["manufacturer"].queryset.values_list("pk", flat=True)) == {
        Manufacturer.objects.get(code="tenant-admin-manufacturer").pk,
        second_manufacturer.pk,
    }
    assert set(form.fields["location"].queryset.values_list("pk", flat=True)) == {
        tenant_admin_graph.allowed_location.pk,
    }
    assert "Second Shared Manufacturer" in rendered_form
    assert "Denied Campus Location" not in rendered_form
    assert "Denied Organization Location" not in rendered_form


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
@pytest.mark.parametrize(
    ("msp_enabled", "multi_site_enabled"),
    [(True, False), (False, True)],
    ids=["msp", "multi-site"],
)
def test_wall_section_inline_rejects_cross_tenant_chargers(
    tenant_admin_graph: TenantAdminGraph,
    settings,
    msp_enabled: bool,
    multi_site_enabled: bool,
) -> None:
    """Inline widgets and forged values share the standalone admin tenant boundary."""
    settings.MICBOARD_MSP_ENABLED = msp_enabled
    settings.MICBOARD_MULTI_SITE_MODE = multi_site_enabled
    settings.MICBOARD_ALLOW_CROSS_ORG_VIEW = False
    if multi_site_enabled:
        site, _created = Site.objects.get_or_create(
            pk=settings.SITE_ID,
            defaults={"domain": "allowed.example.test", "name": "Allowed Site"},
        )
        tenant_admin_graph.allowed_location.building.site = site
        tenant_admin_graph.allowed_location.building.save(update_fields=["site"])
    inline = WallSectionInline(DisplayWall, AdminSite())

    formfield = inline.formfield_for_manytomany(
        WallSection._meta.get_field("chargers"),
        _request_for(tenant_admin_graph.staff_user),
    )

    assert set(formfield.queryset.values_list("pk", flat=True)) == {
        tenant_admin_graph.allowed_charger.pk,
    }
    with pytest.raises(ValidationError, match="valid choice"):
        formfield.clean([tenant_admin_graph.denied_campus_charger.pk])


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_rf_channel_inline_scopes_and_binds_active_units_to_parent_chassis(
    tenant_admin_graph: TenantAdminGraph,
) -> None:
    """RF inline choices cannot cross either tenant or chassis boundaries."""
    user = tenant_admin_graph.staff_user
    user.user_permissions.add(
        Permission.objects.get(codename="view_rfchannel"),
        Permission.objects.get(codename="add_rfchannel"),
        Permission.objects.get(codename="change_rfchannel"),
    )
    allowed_unit = WirelessUnitFactory(
        base_chassis=tenant_admin_graph.allowed_chassis,
        manufacturer=tenant_admin_graph.allowed_chassis.manufacturer,
    )
    same_tenant_chassis = WirelessChassisFactory(
        manufacturer=tenant_admin_graph.allowed_chassis.manufacturer,
        location=tenant_admin_graph.allowed_location,
    )
    same_tenant_other_unit = WirelessUnitFactory(
        base_chassis=same_tenant_chassis,
        manufacturer=same_tenant_chassis.manufacturer,
    )
    denied_unit = WirelessUnitFactory(
        base_chassis=tenant_admin_graph.denied_campus_chassis,
        manufacturer=tenant_admin_graph.denied_campus_chassis.manufacturer,
    )
    monitoring_group = MonitoringGroup.objects.create(name="Inline Allowed Hardware")
    monitoring_group.users.add(user)
    MonitoringGroupLocation.objects.create(
        monitoring_group=monitoring_group,
        location=tenant_admin_graph.allowed_location,
    )
    inline = RFChannelInline(WirelessChassis, AdminSite())
    request = _request_for(user)

    tenant_field = inline.formfield_for_foreignkey(
        inline.model._meta.get_field("active_wireless_unit"),
        request,
    )
    assert set(tenant_field.queryset.values_list("pk", flat=True)) == {
        allowed_unit.pk,
        same_tenant_other_unit.pk,
    }
    assert denied_unit.pk not in tenant_field.queryset.values_list("pk", flat=True)

    formset_class = inline.get_formset(request, tenant_admin_graph.allowed_chassis)
    formset = formset_class(instance=tenant_admin_graph.allowed_chassis)
    active_unit_field = formset.forms[0].fields["active_wireless_unit"]
    assert set(active_unit_field.queryset.values_list("pk", flat=True)) == {allowed_unit.pk}
    with pytest.raises(ValidationError, match="valid choice"):
        active_unit_field.clean(same_tenant_other_unit.pk)


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_unscoped_admin_model_fails_closed(tenant_admin_graph: TenantAdminGraph) -> None:
    """Models without a safe tenant lookup cannot leak through admin in MSP mode."""
    model_admin = ManufacturerAdmin(Manufacturer, admin.site)

    assert not model_admin.get_queryset(_request_for(tenant_admin_graph.staff_user)).exists()


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=True)
def test_platform_superuser_can_manage_global_catalog_in_multi_site_mode(
    tenant_admin_graph: TenantAdminGraph,
) -> None:
    """Platform catalogs remain manageable despite having no tenant key."""
    superuser = User.objects.create_superuser(username="platform-catalog-admin")
    model_admin = ManufacturerAdmin(Manufacturer, admin.site)

    assert set(model_admin.get_queryset(_request_for(superuser)).values_list("pk", flat=True)) == {
        Manufacturer.objects.get(code="tenant-admin-manufacturer").pk,
    }


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=True)
def test_global_catalog_still_fails_closed_for_non_superuser(
    tenant_admin_graph: TenantAdminGraph,
) -> None:
    """A staff permission does not grant host-wide data access in multi-site mode."""
    tenant_admin_graph.staff_user.user_permissions.add(
        Permission.objects.get(codename="view_manufacturer")
    )
    model_admin = ManufacturerAdmin(Manufacturer, admin.site)

    assert not model_admin.get_queryset(_request_for(tenant_admin_graph.staff_user)).exists()


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_realtime_connection_admin_inherits_chassis_tenant_scope(
    tenant_admin_graph: TenantAdminGraph,
) -> None:
    """Real-time operations must expose only connections for visible chassis."""
    allowed = RealTimeConnection.objects.create(
        chassis=tenant_admin_graph.allowed_chassis,
        connection_type="sse",
    )
    RealTimeConnection.objects.create(
        chassis=tenant_admin_graph.denied_campus_chassis,
        connection_type="sse",
    )
    model_admin = RealTimeConnectionAdmin(RealTimeConnection, AdminSite())

    visible_ids = set(
        model_admin.get_queryset(_request_for(tenant_admin_graph.staff_user)).values_list(
            "pk",
            flat=True,
        )
    )

    assert visible_ids == {allowed.pk}
    assert model_admin.fieldsets[0][1]["fields"][0] == "chassis"


@pytest.mark.django_db
def test_tenant_boundary_admin_is_superuser_only(tenant_admin_graph: TenantAdminGraph) -> None:
    """Tenant membership administration is a platform-level operation."""
    model_admin = SuperuserOnlyAdmin(Organization, AdminSite())
    staff_request = _request_for(tenant_admin_graph.staff_user)

    assert not model_admin.get_queryset(staff_request).exists()
    assert not model_admin.has_module_permission(staff_request)
    assert not model_admin.has_view_permission(staff_request)
    assert not model_admin.has_add_permission(staff_request)
    assert not model_admin.has_change_permission(staff_request)
    assert not model_admin.has_delete_permission(staff_request)

    superuser_request = _request_for(User.objects.create_superuser(username="platform-admin"))
    assert model_admin.get_queryset(superuser_request).exists()
    assert model_admin.has_module_permission(superuser_request)


@pytest.mark.django_db
@override_settings(
    MICBOARD_MSP_ENABLED=False,
    MICBOARD_MULTI_SITE_MODE=True,
    SITE_ID=1,
)
def test_admin_queryset_and_related_choices_are_site_scoped() -> None:
    """Multi-site mode must isolate both changelists and relationship widgets."""
    current_site = Site.objects.get(pk=1)
    other_site = Site.objects.create(domain="other.example.test", name="Other")
    manufacturer = Manufacturer.objects.create(name="Site Manufacturer", code="site-mfr")
    user = User.objects.create_user(username="site-admin", is_staff=True)

    def create_chassis(*, site: Site, name: str, ip: str) -> WirelessChassis:
        building = Building.objects.create(name=f"{name} Building", site=site)
        location = Location.objects.create(name=f"{name} Location", building=building)
        return WirelessChassis.objects.create(
            name=name,
            manufacturer=manufacturer,
            api_device_id=name.lower(),
            role="receiver",
            location=location,
            ip=ip,
        )

    allowed = create_chassis(site=current_site, name="Allowed", ip="192.0.2.21")
    denied = create_chassis(site=other_site, name="Denied", ip="192.0.2.22")
    model_admin = WirelessChassisAdmin(WirelessChassis, AdminSite())
    request = _request_for(user)

    assert set(model_admin.get_queryset(request).values_list("pk", flat=True)) == {allowed.pk}
    form = model_admin.get_form(request, obj=allowed)(instance=allowed)
    assert set(form.fields["manufacturer"].queryset.values_list("pk", flat=True)) == {
        manufacturer.pk,
    }
    assert set(form.fields["location"].queryset.values_list("pk", flat=True)) == {
        allowed.location_id,
    }
    assert denied.location_id not in form.fields["location"].queryset.values_list(
        "pk",
        flat=True,
    )
    formfield = model_admin.formfield_for_foreignkey(
        RealTimeConnection._meta.get_field("chassis"),
        request,
    )
    assert set(formfield.queryset.values_list("pk", flat=True)) == {allowed.pk}
    assert denied.pk not in formfield.queryset.values_list("pk", flat=True)
