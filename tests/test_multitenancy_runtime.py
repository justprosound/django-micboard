"""High-value coverage for optional tenant filtering and request resolution."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, Mock, patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings

import pytest

from micboard.models.base_managers import TenantOptimizedManager, TenantOptimizedQuerySet
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.locations import Building, Location
from micboard.models.monitoring.group import MonitoringGroup
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.models.rf_coordination.rf_channel import RFChannel
from micboard.multitenancy.middleware import (
    TenantMiddleware,
    _get_org_from_membership,
    _get_org_from_session,
    _get_org_from_subdomain,
    _get_org_from_user_profile,
    get_current_campus,
    get_current_organization,
)
from micboard.multitenancy.models import Campus, Organization, OrganizationMembership
from micboard.services.core.performer_assignment import PerformerAssignmentService
from micboard.services.monitoring.monitoring_access import MonitoringService

_for_user = cast(Any, TenantOptimizedQuerySet.for_user)


def _queryset_with_model(**attributes: object) -> Any:
    queryset = MagicMock()
    queryset.model = type("TenantModel", (), attributes)
    return queryset


@override_settings(MICBOARD_MULTI_SITE_MODE=False)
def test_site_filter_is_noop_when_disabled() -> None:
    queryset = _queryset_with_model(site_id=None)
    assert TenantOptimizedQuerySet.for_site(queryset, site_id=4) is queryset


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        ("site_id", {"site_id": 7}),
        ("building", {"building__site_id": 7}),
        ("location", {"location__building__site_id": 7}),
    ],
)
@override_settings(MICBOARD_MULTI_SITE_MODE=True, SITE_ID=7)
def test_site_filter_uses_available_tenant_path(attribute: str, expected: dict[str, int]) -> None:
    queryset = _queryset_with_model(**{attribute: object()})
    result = TenantOptimizedQuerySet.for_site(queryset)
    assert result is queryset.filter.return_value
    queryset.filter.assert_called_once_with(**expected)


@override_settings(MICBOARD_MULTI_SITE_MODE=True)
def test_site_filter_leaves_unscoped_model_unchanged() -> None:
    queryset = _queryset_with_model()
    assert TenantOptimizedQuerySet.for_site(queryset, site_id=3) is queryset


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        ("organization_id", {"organization_id": 9}),
        ("building", {"building__organization_id": 9}),
        ("location", {"location__building__organization_id": 9}),
        ("campus", {"campus__organization_id": 9}),
    ],
)
@override_settings(MICBOARD_MSP_ENABLED=True)
def test_organization_filter_uses_available_tenant_path(
    attribute: str, expected: dict[str, int]
) -> None:
    queryset = _queryset_with_model(**{attribute: object()})
    organization = SimpleNamespace(id=9)
    result = TenantOptimizedQuerySet.for_organization(
        queryset,
        organization=cast(Any, organization),
    )
    assert result is queryset.filter.return_value
    queryset.filter.assert_called_once_with(**expected)


@override_settings(MICBOARD_MSP_ENABLED=False)
def test_organization_and_campus_filters_are_noops_when_disabled() -> None:
    queryset = _queryset_with_model(organization_id=None, campus_id=None)
    assert TenantOptimizedQuerySet.for_organization(queryset, organization=1) is queryset
    assert TenantOptimizedQuerySet.for_campus(queryset, campus_id=1) is queryset


@override_settings(MICBOARD_MSP_ENABLED=True)
def test_organization_and_campus_filters_allow_missing_context() -> None:
    queryset = _queryset_with_model()
    assert TenantOptimizedQuerySet.for_organization(queryset) is queryset
    assert TenantOptimizedQuerySet.for_campus(queryset) is queryset


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        ("campus_id", {"campus_id": 5}),
        ("building", {"building__campus_id": 5}),
        ("location", {"location__building__campus_id": 5}),
    ],
)
@override_settings(MICBOARD_MSP_ENABLED=True)
def test_campus_filter_uses_available_tenant_path(attribute: str, expected: dict[str, int]) -> None:
    queryset = _queryset_with_model(**{attribute: object()})
    result = TenantOptimizedQuerySet.for_campus(queryset, campus_id=5)
    assert result is queryset.filter.return_value
    queryset.filter.assert_called_once_with(**expected)


@override_settings(MICBOARD_MSP_ENABLED=True)
@patch.object(OrganizationMembership._default_manager, "filter")
def test_msp_user_filter_denies_users_without_memberships(mock_filter: MagicMock) -> None:
    queryset = _queryset_with_model(organization_id=None)
    queryset.none.return_value = "none"
    mock_filter.return_value.values_list.return_value = []
    user = SimpleNamespace(is_superuser=False)
    assert _for_user(queryset, user=user) == "none"


@override_settings(MICBOARD_MSP_ENABLED=True)
@patch.object(OrganizationMembership._default_manager, "filter")
def test_msp_user_filter_applies_every_membership(mock_filter: MagicMock) -> None:
    queryset = _queryset_with_model(organization_id=None)
    queryset._for_memberships.return_value = queryset
    memberships = [(2, None), (3, 5)]
    mock_filter.return_value.values_list.return_value = memberships
    user = SimpleNamespace(is_superuser=False)
    assert _for_user(queryset, user=user) is queryset
    queryset._for_memberships.assert_called_once_with(memberships)


@override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=True)
def test_multisite_user_filter_delegates_to_site_filter() -> None:
    queryset = _queryset_with_model()
    user = SimpleNamespace(is_superuser=False)
    assert _for_user(queryset, user=user) is queryset.for_site.return_value


@override_settings(
    MICBOARD_MSP_ENABLED=False,
    MICBOARD_MULTI_SITE_MODE=False,
    MICBOARD_ALLOW_CROSS_ORG_VIEW=True,
)
def test_superuser_and_original_user_filters_are_preserved() -> None:
    queryset = _queryset_with_model()
    assert _for_user(queryset, user=SimpleNamespace(is_superuser=True)) is queryset


@override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=False)
@patch("micboard.services.monitoring.monitoring_access.MonitoringService.get_accessible_locations")
def test_monitoring_group_fallback_is_scoped(mock_locations: MagicMock) -> None:
    queryset = SimpleNamespace(
        model=type("LocatedModel", (), {"location": object()}),
        filter=Mock(),
    )
    locations = MagicMock()
    mock_locations.return_value = locations
    user = SimpleNamespace(
        is_superuser=False,
        monitoring_groups=MagicMock(),
    )

    assert _for_user(queryset, user=user) is queryset.filter.return_value
    queryset.filter.assert_called_once_with(location__in=locations)


def test_manager_methods_delegate_to_tenant_queryset() -> None:
    manager = cast(Any, TenantOptimizedManager())
    manager.get_queryset = Mock()
    queryset = manager.get_queryset.return_value
    manager.for_site(site_id=1)
    manager.for_organization(organization=2)
    manager.for_campus(campus_id=3)
    manager.for_user(user=Mock())
    queryset.for_site.assert_called_once_with(site_id=1)
    queryset.for_organization.assert_called_once_with(organization=2)
    queryset.for_campus.assert_called_once_with(campus_id=3)
    queryset.for_user.assert_called_once()


def _request(**kwargs: Any) -> Any:
    defaults = {
        "user": SimpleNamespace(is_authenticated=False, is_superuser=False),
        "session": {},
        "get_host": lambda: "tenant.example.test",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@patch.object(Organization._default_manager, "get")
def test_session_organization_accepts_superuser_and_clears_denied_access(
    mock_get: MagicMock,
) -> None:
    organization = SimpleNamespace(pk=4, is_active=True)
    mock_get.return_value = organization
    super_request = _request(
        session={"current_organization_id": 4},
        user=SimpleNamespace(is_authenticated=True, is_superuser=True),
    )
    assert _get_org_from_session(super_request) is organization

    denied_request = _request(
        session={"current_organization_id": 4},
        user=SimpleNamespace(is_authenticated=True, is_superuser=False),
    )
    with patch.object(OrganizationMembership._default_manager, "filter") as membership_filter:
        membership_filter.return_value.exists.return_value = False
        assert _get_org_from_session(denied_request) is None
    assert "current_organization_id" not in denied_request.session


@patch.object(Organization._default_manager, "get", side_effect=Organization.DoesNotExist)
def test_session_organization_clears_deleted_organization(_mock_get: MagicMock) -> None:
    request = _request(session={"current_organization_id": 99})
    assert _get_org_from_session(request) is None
    assert request.session == {}
    assert _get_org_from_session(cast(Any, SimpleNamespace(user=request.user))) is None


def test_profile_organization_requires_authenticated_active_profile() -> None:
    active = SimpleNamespace(is_active=True)
    user = SimpleNamespace(
        is_authenticated=True,
        profile=SimpleNamespace(default_organization=active),
    )
    assert _get_org_from_user_profile(_request(user=user)) is active
    assert _get_org_from_user_profile(_request()) is None


@patch.object(OrganizationMembership._default_manager, "filter")
def test_membership_organization_returns_only_active_organization(mock_filter: MagicMock) -> None:
    active = SimpleNamespace(is_active=True)
    chain = mock_filter.return_value.select_related.return_value.order_by.return_value
    chain.first.return_value = SimpleNamespace(organization=active)
    user = SimpleNamespace(is_authenticated=True)
    assert _get_org_from_membership(_request(user=user)) is active
    assert _get_org_from_membership(_request()) is None


@override_settings(MICBOARD_SUBDOMAIN_ROUTING=True, MICBOARD_ROOT_DOMAIN="example.test")
@patch.object(Organization._default_manager, "get")
def test_subdomain_organization_resolves_valid_tenant(mock_get: MagicMock) -> None:
    organization = object()
    mock_get.return_value = organization
    assert _get_org_from_subdomain(_request()) is organization
    mock_get.assert_called_once_with(slug="tenant", is_active=True)


@override_settings(MICBOARD_SUBDOMAIN_ROUTING=True, MICBOARD_ROOT_DOMAIN="example.test")
def test_subdomain_organization_rejects_invalid_hosts() -> None:
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
    request = _request()
    session_org.return_value = None
    profile_org.return_value = None
    membership_org.return_value = "membership"
    assert get_current_organization(request) == "membership"
    subdomain_org.assert_not_called()


@override_settings(MICBOARD_MSP_ENABLED=False)
def test_tenant_resolution_is_disabled_by_default() -> None:
    request = _request()
    assert get_current_organization(request) is None
    assert get_current_campus(request) is None


@override_settings(MICBOARD_MSP_ENABLED=True)
@patch.object(OrganizationMembership._default_manager, "filter")
def test_current_campus_prefers_session_then_membership(mock_filter: MagicMock) -> None:
    request = _request(session={"current_campus_id": 6})
    assert get_current_campus(request) == 6

    request = _request(
        user=SimpleNamespace(is_authenticated=True),
        organization=object(),
    )
    mock_filter.return_value.first.return_value = SimpleNamespace(campus_id=8)
    assert get_current_campus(request) == 8


@patch("micboard.multitenancy.middleware.get_current_campus", return_value=7)
@patch("micboard.multitenancy.middleware.get_current_organization", return_value="org")
def test_tenant_middleware_attaches_lazy_context(
    _organization: MagicMock, _campus: MagicMock
) -> None:
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
        role="operator",
    )
    OrganizationMembership.objects.create(
        user=user,
        organization=second_org,
        campus=allowed_campus,
        role="operator",
    )

    manufacturer = Manufacturer.objects.create(name="Tenant hardware", code="tenant-hardware")

    def create_chassis(
        name: str,
        organization_id: int,
        campus_id: int | None = None,
    ) -> WirelessChassis:
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

    visible_ids = set(WirelessChassis.objects.for_user(user=user).values_list("pk", flat=True))
    assert visible_ids == {first.pk, allowed.pk}
    assert denied.pk not in visible_ids


@pytest.mark.django_db
def test_building_rejects_campus_from_another_organization() -> None:
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

    organization_scope = TenantOptimizedQuerySet(
        Organization,
        using="default",
    ).for_user(user=user)
    campus_scope = TenantOptimizedQuerySet(Campus, using="default").for_user(user=user)

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

    assert set(WirelessUnit.objects.for_user(user=user)) == {allowed_unit}
    assert set(RFChannel.objects.for_user(user=user)) == set(
        allowed_unit.base_chassis.rf_channels.all()
    )
    assert (
        not RFChannel.objects.for_user(user=user).filter(chassis=denied_unit.base_chassis).exists()
    )
    assert set(PerformerAssignment.objects.for_user(user=user)) == {allowed_assignment}
    assert set(Performer.objects.for_user(user=user)) == {allowed_performer}
    assert denied_assignment not in PerformerAssignment.objects.for_user(user=user)
    assert unassigned_performer not in Performer.objects.for_user(user=user)
    assert set(MonitoringService.get_accessible_locations(user)) == {
        allowed_unit.base_chassis.location
    }
    assert set(MonitoringService.get_accessible_buildings(user)) == {
        allowed_unit.base_chassis.location.building
    }


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
            assignment_id=assignment.pk,
            user=user,
            notes="viewer mutation",
        )
    with pytest.raises(PermissionDenied):
        PerformerAssignmentService.create_assignment(
            performer_id=performer.pk,
            unit_id=second_unit.pk,
            group_id=group.pk,
            user=user,
        )

    membership.role = "operator"
    membership.save(update_fields=["role"])
    updated = PerformerAssignmentService.update_assignment(
        assignment_id=assignment.pk,
        user=user,
        notes="operator mutation",
    )
    assert updated.notes == "operator mutation"
