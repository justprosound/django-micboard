"""High-value coverage for optional tenant filtering and request resolution."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, Mock, patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings

import pytest

from micboard.models.base_managers import TenantOptimizedQuerySet
from micboard.models.base_managers import site_lookup as base_site_lookup
from micboard.models.base_managers import tenant_lookups as base_tenant_lookups
from micboard.models.discovery.discovery_queue import DeviceMovementLog
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.charger import ChargerSlot
from micboard.models.hardware.display_wall import WallSection
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.locations.structure import Building, Location
from micboard.models.monitoring.alert import Alert
from micboard.models.monitoring.group import MonitoringGroup
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.models.rf_coordination.rf_channel import RFChannel
from micboard.multitenancy.middleware import (
    TenantMiddleware,
    _get_org_from_session,
    _get_org_from_subdomain,
    get_current_campus,
    get_current_organization,
)
from micboard.multitenancy.models import Campus, Organization, OrganizationMembership
from micboard.services.core.performer_assignment import PerformerAssignmentService
from micboard.services.core.performer_assignment_dtos import (
    CreatePerformerAssignment,
    UpdatePerformerAssignment,
)
from micboard.services.shared.visibility import visible_to


def _queryset_with_model(**attributes: object) -> Any:
    """
    Build a mock queryset and assign it a dynamically created model class.

    This helper streamlines the mock setup for tenant scoping tests, significantly
    improving test setup brevity and readability.
    """
    queryset = MagicMock()
    queryset.model = type("TenantModel", (), attributes)
    return queryset


@override_settings(MICBOARD_MULTI_SITE_MODE=False)
def test_site_filter_is_noop_when_disabled() -> None:
    """Verify that site filter is noop when disabled."""
    queryset = _queryset_with_model(site_id=None)
    assert TenantOptimizedQuerySet.for_site(queryset, site_id=4) is queryset


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        ("site_id", {"site_id": 7}),
        ("building", {"building__site_id": 7}),
        ("location", {"location__building__site_id": 7}),
        ("base_chassis", {"base_chassis__location__building__site_id": 7}),
        ("chassis", {"chassis__location__building__site_id": 7}),
        (
            "wireless_unit",
            {"wireless_unit__base_chassis__location__building__site_id": 7},
        ),
        ("organization", {"organization__site_id": 7}),
    ],
)
@override_settings(MICBOARD_MULTI_SITE_MODE=True, SITE_ID=7)
def test_site_filter_uses_available_tenant_path(attribute: str, expected: dict[str, int]) -> None:
    """Verify that site filter uses available tenant path."""
    queryset = _queryset_with_model(**{attribute: object()})
    result = TenantOptimizedQuerySet.for_site(queryset)
    assert result is queryset.filter.return_value.distinct.return_value
    queryset.filter.assert_called_once_with(**expected)


@override_settings(MICBOARD_MULTI_SITE_MODE=True)
def test_site_filter_fails_closed_for_unscoped_model() -> None:
    """Verify that site filter fails closed for unscoped model."""
    queryset = _queryset_with_model()
    assert TenantOptimizedQuerySet.for_site(queryset, site_id=3) is queryset.none.return_value


@pytest.mark.parametrize(
    ("model", "tenant_lookups", "site_lookup"),
    [
        (
            ChargerSlot,
            (
                "charger__location__building__organization_id",
                "charger__location__building__campus_id",
            ),
            "charger__location__building__site_id",
        ),
        (
            WallSection,
            (
                "wall__location__building__organization_id",
                "wall__location__building__campus_id",
            ),
            "wall__location__building__site_id",
        ),
        (
            DeviceMovementLog,
            (
                "device__location__building__organization_id",
                "device__location__building__campus_id",
            ),
            "device__location__building__site_id",
        ),
        (
            Alert,
            (
                "channel__chassis__location__building__organization_id",
                "channel__chassis__location__building__campus_id",
            ),
            "channel__chassis__location__building__site_id",
        ),
    ],
)
@override_settings(MICBOARD_MULTI_SITE_MODE=True)
def test_nested_tenant_models_use_explicit_reviewed_ownership_paths(
    model: type,
    tenant_lookups: tuple[str, str],
    site_lookup: str,
) -> None:
    """Nested operational records must remain usable without widening tenant scope."""
    queryset = TenantOptimizedQuerySet(model, using="default")

    assert base_tenant_lookups(model) == tenant_lookups
    assert base_site_lookup(model) == site_lookup
    assert "SELECT" in str(queryset.for_site(site_id=1).query)
    assert "SELECT" in str(queryset.for_memberships([(1, 2)]).query)


def _request(**kwargs: Any) -> Any:
    """Helper to request."""
    defaults = {
        "user": SimpleNamespace(is_authenticated=False, is_superuser=False),
        "session": {},
        "get_host": lambda: "tenant.example.test",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@patch.object(Organization._default_manager, "get", side_effect=Organization.DoesNotExist)
def test_session_organization_clears_deleted_organization(_mock_get: MagicMock) -> None:
    """Verify that session organization clears deleted organization."""
    request = _request(session={"current_organization_id": 99})
    assert _get_org_from_session(request) is None
    assert request.session == {}
    assert _get_org_from_session(cast(Any, SimpleNamespace(user=request.user))) is None


@override_settings(MICBOARD_SUBDOMAIN_ROUTING=True, MICBOARD_ROOT_DOMAIN="example.test")
@patch.object(Organization._default_manager, "get")
def test_subdomain_organization_resolves_valid_tenant(mock_get: MagicMock) -> None:
    """Verify that subdomain organization resolves valid tenant."""
    organization = object()
    mock_get.return_value = organization
    assert _get_org_from_subdomain(_request()) is organization
    mock_get.assert_called_once_with(slug="tenant", is_active=True)


@override_settings(MICBOARD_SUBDOMAIN_ROUTING=True, MICBOARD_ROOT_DOMAIN="example.test")
def test_subdomain_organization_rejects_invalid_hosts() -> None:
    """Verify that subdomain organization rejects invalid hosts."""
    assert _get_org_from_subdomain(_request(get_host=lambda: "www.example.test")) is None
    assert _get_org_from_subdomain(_request(get_host=lambda: "tenant.other.test")) is None


@override_settings(MICBOARD_MSP_ENABLED=True)
@patch("micboard.multitenancy.middleware._get_org_from_subdomain")
@patch("micboard.multitenancy.middleware._get_org_from_membership")
@patch("micboard.multitenancy.middleware._get_org_from_user_profile")
@patch("micboard.multitenancy.middleware._get_org_from_session")
def test_current_organization_uses_priority_order(
    session_org: MagicMock,
    profile_org: MagicMock,
    membership_org: MagicMock,
    subdomain_org: MagicMock,
) -> None:
    """Verify that current organization uses priority order."""
    request = _request()
    session_org.return_value = None
    profile_org.return_value = None
    membership_org.return_value = "membership"
    assert get_current_organization(request) == "membership"
    subdomain_org.assert_not_called()


@override_settings(MICBOARD_MSP_ENABLED=False)
def test_tenant_resolution_is_disabled_by_default() -> None:
    """Verify that tenant resolution is disabled by default."""
    request = _request()
    assert get_current_organization(request) is None
    assert get_current_campus(request) is None


@patch("micboard.multitenancy.middleware.get_current_campus", return_value=7)
@patch("micboard.multitenancy.middleware.get_current_organization", return_value="org")
def test_tenant_middleware_attaches_lazy_context(
    _organization: MagicMock, _campus: MagicMock
) -> None:
    """Verify that tenant middleware attaches lazy context."""
    downstream = Mock(side_effect=lambda request: (request.organization, request.campus_id))
    request = _request()
    response = TenantMiddleware(downstream)(request)
    assert str(response[0]) == "org"
    assert response[1] == 7


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_real_manager_unions_organizations_and_honors_campus_scope(django_user_model) -> None:
    """Real ORM filtering must union memberships without crossing campuses."""
    user = django_user_model.objects.create_user(username="tenant-operator")
    first_org = Organization.objects.create(name="First tenant", slug="first-tenant")
    second_org = Organization.objects.create(name="Second tenant", slug="second-tenant")
    allowed_campus = Campus.objects.create(
        organization=second_org,
        name="Allowed campus",
        slug="allowed-campus",
    )
    denied_campus = Campus.objects.create(
        organization=second_org,
        name="Denied campus",
        slug="denied-campus",
    )
    OrganizationMembership.objects.create(
        user=user,
        organization=first_org,
        role="admin",
    )
    OrganizationMembership.objects.create(
        user=user,
        organization=second_org,
        campus=allowed_campus,
        role="admin",
    )

    manufacturer = Manufacturer.objects.create(name="Tenant hardware", code="tenant-hardware")

    def create_chassis(
        name: str,
        organization_id: int,
        campus_id: int | None = None,
    ) -> WirelessChassis:
        """Helper to create chassis."""
        building = Building.objects.create(
            name=f"{name} building",
            organization_id=organization_id,
            campus_id=campus_id,
        )
        location = Location.objects.create(building=building, name=f"{name} location")
        return WirelessChassis.objects.create(
            name=name,
            manufacturer=manufacturer,
            api_device_id=name.lower().replace(" ", "-"),
            role="receiver",
            ip=f"192.0.2.{10 + WirelessChassis.objects.count()}",
            location=location,
        )

    first = create_chassis("First", first_org.pk)
    allowed = create_chassis("Allowed", second_org.pk, allowed_campus.pk)
    denied = create_chassis("Denied", second_org.pk, denied_campus.pk)

    visible_ids = set(visible_to(WirelessChassis, user=user).values_list("pk", flat=True))
    assert visible_ids == {first.pk, allowed.pk}
    assert denied.pk not in visible_ids


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_real_manager_rejects_revoked_and_inconsistent_memberships(django_user_model) -> None:
    """Inactive or cross-tenant membership context must never grant visibility."""
    user = django_user_model.objects.create_user(username="revoked-tenant-operator")
    broad_org = Organization.objects.create(name="Broad tenant", slug="broad-tenant")
    scoped_org = Organization.objects.create(name="Scoped tenant", slug="scoped-tenant")
    scoped_campus = Campus.objects.create(
        organization=scoped_org,
        name="Scoped campus",
        slug="scoped-campus",
    )
    inactive_org = Organization.objects.create(
        name="Inactive tenant",
        slug="inactive-tenant",
        is_active=False,
    )
    inactive_campus_org = Organization.objects.create(
        name="Inactive campus tenant",
        slug="inactive-campus-tenant",
    )
    inactive_campus = Campus.objects.create(
        organization=inactive_campus_org,
        name="Inactive campus",
        slug="inactive-campus",
        is_active=False,
    )
    inconsistent_org = Organization.objects.create(
        name="Inconsistent tenant",
        slug="inconsistent-tenant",
    )
    foreign_org = Organization.objects.create(name="Foreign tenant", slug="foreign-tenant")
    foreign_campus = Campus.objects.create(
        organization=foreign_org,
        name="Foreign campus",
        slug="foreign-campus",
    )

    OrganizationMembership.objects.create(user=user, organization=broad_org, role="admin")
    OrganizationMembership.objects.create(
        user=user,
        role="admin",
        organization=scoped_org,
        campus=scoped_campus,
    )
    OrganizationMembership.objects.create(user=user, organization=inactive_org, role="admin")
    OrganizationMembership.objects.create(
        user=user,
        role="admin",
        organization=inactive_campus_org,
        campus=inactive_campus,
    )
    OrganizationMembership.objects.create(
        user=user,
        role="admin",
        organization=inconsistent_org,
        campus=foreign_campus,
    )

    manufacturer = Manufacturer.objects.create(
        name="Revocation hardware",
        code="revocation-hardware",
    )

    def create_chassis(
        name: str,
        organization: Organization,
        campus: Campus | None = None,
    ) -> WirelessChassis:
        """Helper to create chassis."""
        building = Building.objects.create(
            name=f"{name} building",
            organization_id=organization.pk,
            campus_id=campus.pk if campus else None,
        )
        location = Location.objects.create(building=building, name=f"{name} location")
        return WirelessChassis.objects.create(
            name=name,
            manufacturer=manufacturer,
            api_device_id=name.lower().replace(" ", "-"),
            role="receiver",
            ip=f"198.51.100.{10 + WirelessChassis.objects.count()}",
            location=location,
        )

    broad = create_chassis("Broad", broad_org)
    scoped = create_chassis("Scoped", scoped_org, scoped_campus)
    create_chassis("Inactive organization", inactive_org)
    create_chassis("Inactive campus", inactive_campus_org, inactive_campus)
    create_chassis("Inconsistent", inconsistent_org)

    visible_ids = set(visible_to(WirelessChassis, user=user).values_list("pk", flat=True))
    assert visible_ids == {broad.pk, scoped.pk}


@pytest.mark.django_db
def test_building_rejects_campus_from_another_organization() -> None:
    """Verify that building rejects campus from another organization."""
    first_org = Organization.objects.create(name="Validation tenant", slug="validation-tenant")
    second_org = Organization.objects.create(name="Other tenant", slug="other-tenant")
    campus = Campus.objects.create(
        organization=second_org,
        name="Other campus",
        slug="other-campus",
    )
    building = Building(
        name="Invalid building",
        organization_id=first_org.pk,
        campus_id=campus.pk,
    )

    with pytest.raises(ValidationError, match="Campus must belong"):
        building.full_clean()


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_tenant_resolver_scopes_organization_and_campus_models(django_user_model) -> None:
    """Direct tenant models must honor organization-wide and campus-only membership."""
    user = django_user_model.objects.create_user(username="tenant-model-viewer")
    organization_wide = Organization.objects.create(name="Whole org", slug="whole-org")
    campus_limited = Organization.objects.create(name="Campus org", slug="campus-org")
    allowed_campus = Campus.objects.create(
        organization=campus_limited,
        name="Allowed direct campus",
        slug="allowed-direct-campus",
    )
    denied_campus = Campus.objects.create(
        organization=campus_limited,
        name="Denied direct campus",
        slug="denied-direct-campus",
    )
    whole_org_campus = Campus.objects.create(
        organization=organization_wide,
        name="Whole org campus",
        slug="whole-org-campus",
    )
    OrganizationMembership.objects.create(user=user, organization=organization_wide)
    OrganizationMembership.objects.create(
        user=user,
        organization=campus_limited,
        campus=allowed_campus,
    )

    organization_scope = visible_to(Organization, user=user, using="default")
    campus_scope = visible_to(Campus, user=user, using="default")

    assert set(organization_scope) == {organization_wide, campus_limited}
    assert set(campus_scope) == {whole_org_campus, allowed_campus}
    assert denied_campus not in campus_scope


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_specialized_managers_compose_monitoring_and_tenant_scope(django_user_model) -> None:
    """Monitoring-group membership must never widen organization access."""
    user = django_user_model.objects.create_user(username="tenant-viewer")
    allowed_org = Organization.objects.create(name="Allowed org", slug="allowed-org")
    denied_org = Organization.objects.create(name="Denied org", slug="denied-org")
    OrganizationMembership.objects.create(user=user, organization=allowed_org, role="viewer")
    group = MonitoringGroup.objects.create(name="Cross-tenant monitoring group")
    group.users.add(user)
    manufacturer = Manufacturer.objects.create(name="Scoped hardware", code="scoped-hardware")

    def create_unit(name: str, organization: Organization, slot: int) -> WirelessUnit:
        """Helper to create unit."""
        building = Building.objects.create(name=f"{name} building", organization_id=organization.pk)
        location = Location.objects.create(building=building, name=f"{name} location")
        group.locations.add(location)
        chassis = WirelessChassis.objects.create(
            name=name,
            manufacturer=manufacturer,
            api_device_id=name.lower(),
            role="receiver",
            ip=f"192.0.2.{organization.pk}",
            location=location,
        )
        return WirelessUnit.objects.create(
            base_chassis=chassis,
            manufacturer=manufacturer,
            slot=slot,
            name=f"{name} unit",
        )

    allowed_unit = create_unit("Allowed", allowed_org, 1)
    denied_unit = create_unit("Denied", denied_org, 2)
    allowed_performer = Performer.objects.create(name="Allowed performer")
    denied_performer = Performer.objects.create(name="Denied performer")
    unassigned_performer = Performer.objects.create(name="Tenantless performer")
    allowed_assignment = PerformerAssignment.objects.create(
        performer=allowed_performer,
        wireless_unit=allowed_unit,
        monitoring_group=group,
    )
    denied_assignment = PerformerAssignment.objects.create(
        performer=denied_performer,
        wireless_unit=denied_unit,
        monitoring_group=group,
    )

    assert set(visible_to(WirelessUnit, user=user)) == {allowed_unit}
    assert set(visible_to(RFChannel, user=user)) == set(allowed_unit.base_chassis.rf_channels.all())
    assert not visible_to(RFChannel, user=user).filter(chassis=denied_unit.base_chassis).exists()
    assert set(visible_to(PerformerAssignment, user=user)) == {allowed_assignment}
    assert set(visible_to(Performer, user=user)) == {allowed_performer}
    assert denied_assignment not in visible_to(PerformerAssignment, user=user)
    assert unassigned_performer not in visible_to(Performer, user=user)
    assert set(visible_to(Location, user=user)) == {allowed_unit.base_chassis.location}
    assert set(visible_to(Building, user=user)) == {allowed_unit.base_chassis.location.building}


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_assignment_writes_require_operator_role(django_user_model) -> None:
    """Viewer membership grants visibility but never assignment mutation."""
    user = django_user_model.objects.create_user(username="read-only-tenant-user")
    organization = Organization.objects.create(name="Role org", slug="role-org")
    membership = OrganizationMembership.objects.create(
        user=user,
        organization=organization,
        role="viewer",
    )
    group = MonitoringGroup.objects.create(name="Role group")
    group.users.add(user)
    building = Building.objects.create(name="Role building", organization_id=organization.pk)
    location = Location.objects.create(building=building, name="Role location")
    group.locations.add(location)
    manufacturer = Manufacturer.objects.create(name="Role hardware", code="role-hardware")
    chassis = WirelessChassis.objects.create(
        manufacturer=manufacturer,
        api_device_id="role-chassis",
        role="receiver",
        ip="192.0.2.50",
        location=location,
    )
    first_unit = WirelessUnit.objects.create(
        base_chassis=chassis,
        manufacturer=manufacturer,
        slot=1,
        name="First role unit",
    )
    second_unit = WirelessUnit.objects.create(
        base_chassis=chassis,
        manufacturer=manufacturer,
        slot=2,
        name="Second role unit",
    )
    performer = Performer.objects.create(name="Role performer")
    assignment = PerformerAssignment.objects.create(
        performer=performer,
        wireless_unit=first_unit,
        monitoring_group=group,
    )

    with pytest.raises(PermissionDenied):
        PerformerAssignmentService.update_assignment(
            command=UpdatePerformerAssignment(
                assignment_id=assignment.pk,
                notes="viewer mutation",
            ),
            user=user,
        )
    with pytest.raises(PermissionDenied):
        PerformerAssignmentService.create_assignment(
            command=CreatePerformerAssignment(
                performer_id=performer.pk,
                unit_id=second_unit.pk,
                group_id=group.pk,
            ),
            user=user,
        )

    membership.role = "operator"
    membership.save(update_fields=["role"])
    updated = PerformerAssignmentService.update_assignment(
        command=UpdatePerformerAssignment(
            assignment_id=assignment.pk,
            notes="operator mutation",
        ),
        user=user,
    )
    assert updated.notes == "operator mutation"
