"""Role-aware tenant mutation policy regressions for Django admin."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission, User
from django.core.exceptions import PermissionDenied
from django.db import models
from django.test import RequestFactory, override_settings

import pytest

from micboard.admin.assignments import PerformerAdmin
from micboard.admin.manufacturers import ManufacturerAdmin
from micboard.admin.mixins import MicboardModelAdmin
from micboard.admin.receivers import WirelessChassisAdmin
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.monitoring.performer import Performer
from micboard.multitenancy.models import Organization, OrganizationMembership
from micboard.services.shared.access_policy import TenantRoleAccessService
from tests.factories.base import UserFactory
from tests.factories.hardware import WirelessChassisFactory
from tests.factories.locations import BuildingFactory, LocationFactory
from tests.factories.monitoring import PerformerAssignmentFactory, PerformerFactory
from tests.factories.multitenancy import OrganizationFactory, OrganizationMembershipFactory

pytestmark = pytest.mark.django_db


def _request_for(user: User, *, method: str = "get") -> Any:
    """Build an admin request with a concrete HTTP safety class."""
    request = getattr(RequestFactory(), method)("/admin/micboard/wirelesschassis/")
    request.user = user
    return request


def _grant_model_permissions(user: User, model: type[models.Model]) -> None:
    """Grant all stock Django permissions so tenant roles remain the only variable."""
    model_name = model._meta.model_name
    permissions = Permission.objects.filter(
        content_type__app_label=model._meta.app_label,
        codename__in={
            f"view_{model_name}",
            f"add_{model_name}",
            f"change_{model_name}",
            f"delete_{model_name}",
        },
    )
    user.user_permissions.add(*permissions)


def _chassis_for(organization: Organization) -> WirelessChassis:
    """Create a chassis whose full ownership path belongs to ``organization``."""
    building = BuildingFactory(organization_id=organization.pk)
    return WirelessChassisFactory(location=LocationFactory(building=building))


@pytest.mark.parametrize("role", ["viewer", "operator"])
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_read_only_roles_keep_admin_visibility_without_generic_crud(role: str) -> None:
    """Django CRUD grants cannot elevate viewer or operator tenant memberships."""
    organization = OrganizationFactory()
    user = UserFactory(is_staff=True)
    _grant_model_permissions(user, WirelessChassis)
    OrganizationMembershipFactory(
        user=user,
        organization=organization,
        campus=None,
        role=role,
    )
    chassis = _chassis_for(organization)
    model_admin = WirelessChassisAdmin(WirelessChassis, AdminSite())
    request = _request_for(user)

    assert model_admin.has_view_permission(request, chassis)
    assert set(model_admin.get_queryset(request).values_list("pk", flat=True)) == {chassis.pk}
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_change_permission(request, chassis)
    assert not model_admin.has_delete_permission(request)
    assert not model_admin.has_delete_permission(request, chassis)


@pytest.mark.parametrize("role", ["admin", "owner"])
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_management_roles_can_crud_only_their_own_scope(role: str) -> None:
    """Admin and owner memberships authorize only objects in their tenant scope."""
    organization = OrganizationFactory()
    foreign_organization = OrganizationFactory()
    user = UserFactory(is_staff=True)
    _grant_model_permissions(user, WirelessChassis)
    OrganizationMembershipFactory(
        user=user,
        organization=organization,
        campus=None,
        role=role,
    )
    own_chassis = _chassis_for(organization)
    foreign_chassis = _chassis_for(foreign_organization)
    model_admin = MicboardModelAdmin(WirelessChassis, AdminSite())
    request = _request_for(user)

    assert model_admin.has_add_permission(request)
    assert model_admin.has_change_permission(request, own_chassis)
    assert model_admin.has_delete_permission(request, own_chassis)
    assert not model_admin.has_change_permission(request, foreign_chassis)
    assert not model_admin.has_delete_permission(request, foreign_chassis)


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_mixed_roles_separate_read_visibility_from_unsafe_admin_querysets() -> None:
    """A viewer tenant stays readable but cannot enter any mutation queryset."""
    managed_organization = OrganizationFactory()
    viewed_organization = OrganizationFactory()
    user = UserFactory(is_staff=True)
    _grant_model_permissions(user, WirelessChassis)
    OrganizationMembershipFactory(
        user=user,
        organization=managed_organization,
        campus=None,
        role="admin",
    )
    OrganizationMembershipFactory(
        user=user,
        organization=viewed_organization,
        campus=None,
        role="viewer",
    )
    managed_chassis = _chassis_for(managed_organization)
    viewed_chassis = _chassis_for(viewed_organization)
    model_admin = MicboardModelAdmin(WirelessChassis, AdminSite())

    readable_ids = set(model_admin.get_queryset(_request_for(user)).values_list("pk", flat=True))
    mutable_ids = set(
        model_admin.get_queryset(_request_for(user, method="post")).values_list(
            "pk",
            flat=True,
        )
    )

    assert readable_ids == {managed_chassis.pk, viewed_chassis.pk}
    assert mutable_ids == {managed_chassis.pk}
    assert model_admin.has_change_permission(_request_for(user), managed_chassis)
    assert not model_admin.has_change_permission(_request_for(user), viewed_chassis)
    with pytest.raises(PermissionDenied):
        model_admin.delete_queryset(
            _request_for(user, method="post"),
            WirelessChassis._default_manager.filter(pk__in=[managed_chassis.pk, viewed_chassis.pk]),
        )
    assert (
        WirelessChassis._default_manager.filter(
            pk__in=[managed_chassis.pk, viewed_chassis.pk]
        ).count()
        == 2
    )


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_tenant_admin_cannot_add_platform_global_manufacturer() -> None:
    """An organization admin is not implicitly a host-wide catalog administrator."""
    organization = OrganizationFactory()
    user = UserFactory(is_staff=True)
    _grant_model_permissions(user, Manufacturer)
    OrganizationMembershipFactory(
        user=user,
        organization=organization,
        campus=None,
        role="admin",
    )
    model_admin = ManufacturerAdmin(Manufacturer, AdminSite())
    request = _request_for(user)

    assert user.has_perm("micboard.add_manufacturer")
    assert not model_admin.has_add_permission(request)


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=True)
def test_unrestricted_superuser_preserves_tenant_and_platform_crud() -> None:
    """The explicit cross-organization superuser bypass remains unrestricted."""
    first = _chassis_for(OrganizationFactory())
    second = _chassis_for(OrganizationFactory())
    Manufacturer.objects.create(name="Platform Catalog", code="platform-catalog")
    user = User.objects.create_superuser(username="unrestricted-platform-admin")
    tenant_admin = MicboardModelAdmin(WirelessChassis, AdminSite())
    performer_admin = PerformerAdmin(Performer, AdminSite())
    manufacturer_admin = ManufacturerAdmin(Manufacturer, AdminSite())
    get_request = _request_for(user)
    post_request = _request_for(user, method="post")

    assert tenant_admin.has_add_permission(get_request)
    assert tenant_admin.has_change_permission(get_request, first)
    assert tenant_admin.has_delete_permission(get_request, second)
    assert set(tenant_admin.get_queryset(get_request).values_list("pk", flat=True)) == {
        first.pk,
        second.pk,
    }
    assert set(tenant_admin.get_queryset(post_request).values_list("pk", flat=True)) == {
        first.pk,
        second.pk,
    }
    assert manufacturer_admin.has_add_permission(get_request)
    assert manufacturer_admin.get_queryset(get_request).count() == 3
    assert performer_admin.has_add_permission(get_request)


@override_settings(
    MICBOARD_MSP_ENABLED=False,
    MICBOARD_MULTI_SITE_MODE=True,
    MICBOARD_ALLOW_CROSS_ORG_VIEW=False,
)
def test_restricted_cross_org_superuser_retains_platform_catalog_crud() -> None:
    """Tenant view restrictions do not remove host-wide superuser authority."""
    manufacturer = Manufacturer.objects.create(
        name="Restricted Platform Catalog",
        code="restricted-platform-catalog",
    )
    user = User.objects.create_superuser(username="restricted-platform-admin")
    model_admin = ManufacturerAdmin(Manufacturer, AdminSite())
    request = _request_for(user)

    assert model_admin.has_add_permission(request)
    assert model_admin.has_change_permission(request, manufacturer)
    assert model_admin.has_delete_permission(request, manufacturer)
    assert manufacturer in model_admin.get_queryset(request)


@override_settings(
    MICBOARD_MSP_ENABLED=True,
    MICBOARD_MULTI_SITE_MODE=True,
    MICBOARD_ALLOW_CROSS_ORG_VIEW=True,
)
def test_multisite_superuser_cannot_create_tenantless_performer() -> None:
    """Multi-site adds stay closed until onboarding can bind a performer atomically."""
    user = User.objects.create_superuser(username="multisite-performer-admin")
    model_admin = PerformerAdmin(Performer, AdminSite())

    assert not model_admin.has_add_permission(_request_for(user))


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_shared_performer_requires_every_assignment_tenant_to_be_writable() -> None:
    """One visible assignment cannot authorize a cross-tenant performer cascade."""
    managed_organization = OrganizationFactory()
    viewed_organization = OrganizationFactory()
    user = UserFactory(is_staff=True)
    _grant_model_permissions(user, Performer)
    OrganizationMembershipFactory(
        user=user,
        organization=managed_organization,
        campus=None,
        role="admin",
    )
    OrganizationMembershipFactory(
        user=user,
        organization=viewed_organization,
        campus=None,
        role="viewer",
    )
    shared_performer = PerformerFactory()
    managed_assignment = PerformerAssignmentFactory(
        performer=shared_performer,
        wireless_unit__base_chassis__location=LocationFactory(
            building=BuildingFactory(organization_id=managed_organization.pk)
        ),
    )
    viewed_assignment = PerformerAssignmentFactory(
        performer=shared_performer,
        wireless_unit__base_chassis__location=LocationFactory(
            building=BuildingFactory(organization_id=viewed_organization.pk)
        ),
    )
    managed_assignment.monitoring_group.users.add(user)
    viewed_assignment.monitoring_group.users.add(user)
    managed_performer = PerformerFactory()
    managed_only_assignment = PerformerAssignmentFactory(
        performer=managed_performer,
        wireless_unit__base_chassis__location=LocationFactory(
            building=BuildingFactory(organization_id=managed_organization.pk)
        ),
    )
    managed_only_assignment.monitoring_group.users.add(user)
    model_admin = PerformerAdmin(Performer, AdminSite())
    request = _request_for(user)

    assert shared_performer in model_admin.get_queryset(request)
    assert not model_admin.has_add_permission(request)
    assert not model_admin.has_change_permission(request, shared_performer)
    assert not model_admin.has_delete_permission(request, shared_performer)
    assert model_admin.has_change_permission(request, managed_performer)
    assert model_admin.has_delete_permission(request, managed_performer)
    with pytest.raises(PermissionDenied):
        model_admin.delete_model(request, shared_performer)
    assert Performer.objects.filter(pk=shared_performer.pk).exists()
    assert viewed_assignment.__class__.objects.filter(pk=viewed_assignment.pk).exists()


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_MULTI_SITE_MODE=True, SITE_ID=7)
def test_management_memberships_use_the_authorized_queryset_database() -> None:
    """Role checks cannot drift from a queued object's database alias."""
    user = UserFactory()
    filtered = MagicMock()
    filtered.filter.return_value = filtered
    filtered.values_list.return_value = [(8, None)]
    database_manager = MagicMock()
    database_manager.filter.return_value = filtered

    with patch.object(
        OrganizationMembership._default_manager,
        "db_manager",
        return_value=database_manager,
    ) as db_manager:
        memberships = TenantRoleAccessService.management_memberships(
            user=user,
            using="replica",
        )

    db_manager.assert_called_once_with("replica")
    assert memberships == [(8, None)]
