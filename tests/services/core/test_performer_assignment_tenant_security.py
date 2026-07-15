"""Tenant-integrity contracts for performer assignments."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import override_settings

import pytest

from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.core.performer_assignment import PerformerAssignmentService
from micboard.services.core.performer_assignment_dtos import (
    CreatePerformerAssignment,
    UpdatePerformerAssignment,
)
from tests.factories.base import UserFactory
from tests.factories.hardware import WirelessChassisFactory, WirelessUnitFactory
from tests.factories.locations import BuildingFactory, LocationFactory
from tests.factories.monitoring import (
    MonitoringGroupFactory,
    MonitoringGroupLocationFactory,
    PerformerAssignmentFactory,
    PerformerFactory,
)
from tests.factories.multitenancy import OrganizationFactory, OrganizationMembershipFactory
from tests.factories.rf_coordination import RFChannelFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def cross_tenant_assignment_graph() -> SimpleNamespace:
    """Build a user who can operate two tenants through distinct monitoring groups."""
    user = UserFactory()
    first_organization = OrganizationFactory()
    second_organization = OrganizationFactory()
    OrganizationMembershipFactory(
        user=user,
        organization=first_organization,
        campus=None,
        role="operator",
    )
    OrganizationMembershipFactory(
        user=user,
        organization=second_organization,
        campus=None,
        role="operator",
    )

    first_location = LocationFactory(
        building=BuildingFactory(organization_id=first_organization.pk),
    )
    second_location = LocationFactory(
        building=BuildingFactory(organization_id=second_organization.pk),
    )
    first_unit = WirelessUnitFactory(
        base_chassis=WirelessChassisFactory(location=first_location),
    )
    second_unit = WirelessUnitFactory(
        base_chassis=WirelessChassisFactory(location=second_location),
    )

    first_group = MonitoringGroupFactory()
    first_group.users.add(user)
    MonitoringGroupLocationFactory(
        monitoring_group=first_group,
        location=first_location,
    )
    second_group = MonitoringGroupFactory()
    second_group.users.add(user)
    MonitoringGroupLocationFactory(
        monitoring_group=second_group,
        location=second_location,
    )

    performer = PerformerFactory()
    PerformerAssignmentFactory(
        performer=performer,
        wireless_unit=first_unit,
        monitoring_group=first_group,
    )
    return SimpleNamespace(
        user=user,
        performer=performer,
        first_group=first_group,
        second_unit=second_unit,
    )


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_create_rejects_group_from_another_unit_tenant(cross_tenant_assignment_graph) -> None:
    """Individually visible objects cannot form a cross-tenant assignment."""
    graph = cross_tenant_assignment_graph

    with pytest.raises(PermissionDenied, match="monitoring group"):
        PerformerAssignmentService.create_assignment(
            command=CreatePerformerAssignment(
                performer_id=graph.performer.pk,
                unit_id=graph.second_unit.pk,
                group_id=graph.first_group.pk,
            ),
            user=graph.user,
        )

    assert not PerformerAssignment.objects.filter(
        performer=graph.performer,
        wireless_unit=graph.second_unit,
    ).exists()


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_update_rejects_legacy_cross_tenant_group(cross_tenant_assignment_graph) -> None:
    """Existing inconsistent rows cannot be modified through the service."""
    graph = cross_tenant_assignment_graph
    legacy_assignment = PerformerAssignmentFactory(
        performer=PerformerFactory(),
        wireless_unit=graph.second_unit,
        monitoring_group=graph.first_group,
    )

    with pytest.raises(PermissionDenied, match="monitoring group"):
        PerformerAssignmentService.update_assignment(
            command=UpdatePerformerAssignment(
                assignment_id=legacy_assignment.pk,
                notes="must not persist",
            ),
            user=graph.user,
        )

    legacy_assignment.refresh_from_db()
    assert legacy_assignment.notes != "must not persist"


@pytest.mark.parametrize("operation", ["delete_assignment", "deactivate_assignment"])
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_destructive_mutations_reject_legacy_cross_tenant_group(
    cross_tenant_assignment_graph,
    operation: str,
) -> None:
    """Every assignment mutation must enforce the group-to-unit tenant relationship."""
    graph = cross_tenant_assignment_graph
    legacy_assignment = PerformerAssignmentFactory(
        performer=PerformerFactory(),
        wireless_unit=graph.second_unit,
        monitoring_group=graph.first_group,
    )

    mutate = getattr(PerformerAssignmentService, operation)
    with pytest.raises(PermissionDenied, match="monitoring group"):
        mutate(assignment_id=legacy_assignment.pk, user=graph.user)

    legacy_assignment.refresh_from_db()
    assert legacy_assignment.is_active is True


@override_settings(MICBOARD_MULTI_SITE_MODE=True)
def test_group_scope_rejects_unit_without_location() -> None:
    """Tenant-aware group checks fail closed when hardware has no managed location."""
    unit = WirelessUnitFactory(base_chassis__location=None)

    with pytest.raises(PermissionDenied, match="managed location"):
        PerformerAssignmentService.ensure_group_can_manage_unit(
            group=MonitoringGroupFactory(),
            unit=unit,
        )


@override_settings(MICBOARD_MULTI_SITE_MODE=True)
def test_group_scope_accepts_building_wide_location_access() -> None:
    """Building-wide group grants cover another room in the same building."""
    building = BuildingFactory()
    managed_location = LocationFactory(building=building)
    unit_location = LocationFactory(building=building)
    group = MonitoringGroupFactory()
    MonitoringGroupLocationFactory(
        monitoring_group=group,
        location=managed_location,
        include_all_rooms=True,
    )
    unit = WirelessUnitFactory(base_chassis__location=unit_location)

    PerformerAssignmentService.ensure_group_can_manage_unit(group=group, unit=unit)


@override_settings(MICBOARD_MULTI_SITE_MODE=True)
def test_group_scope_accepts_explicit_channel_access() -> None:
    """An explicitly managed assigned channel grants unit mutation scope."""
    channel = RFChannelFactory()
    group = MonitoringGroupFactory()
    group.channels.add(channel)
    unit = WirelessUnitFactory(
        base_chassis__location=LocationFactory(),
        assigned_resource=channel,
    )

    PerformerAssignmentService.ensure_group_can_manage_unit(group=group, unit=unit)


@override_settings(MICBOARD_MSP_ENABLED=True)
def test_unit_mutation_fails_closed_without_multitenancy_app() -> None:
    """MSP writes are unavailable when the membership model is not installed."""
    with (
        patch(
            "micboard.services.core.performer_assignment.apps.is_installed",
            return_value=False,
        ),
        pytest.raises(PermissionDenied, match="unavailable"),
    ):
        PerformerAssignmentService.ensure_can_modify_unit(
            user=UserFactory(),
            unit=WirelessUnitFactory(),
        )


@override_settings(MICBOARD_MSP_ENABLED=True)
def test_unit_mutation_requires_an_organization_and_membership() -> None:
    """Unowned hardware and users without an active modifying role both fail closed."""
    user = UserFactory()
    unlocated_unit = WirelessUnitFactory(base_chassis__location=None)
    with pytest.raises(PermissionDenied, match="not assigned to an organization"):
        PerformerAssignmentService.ensure_can_modify_unit(user=user, unit=unlocated_unit)

    unowned_unit = WirelessUnitFactory(base_chassis__location=LocationFactory())

    with pytest.raises(PermissionDenied, match="not assigned to an organization"):
        PerformerAssignmentService.ensure_can_modify_unit(user=user, unit=unowned_unit)

    organization = OrganizationFactory()
    owned_unit = WirelessUnitFactory(
        base_chassis__location=LocationFactory(
            building=BuildingFactory(organization_id=organization.pk),
        ),
    )
    with pytest.raises(PermissionDenied, match="membership"):
        PerformerAssignmentService.ensure_can_modify_unit(user=user, unit=owned_unit)


@override_settings(MICBOARD_MSP_ENABLED=True)
def test_unrestricted_user_can_modify_unlocated_unit() -> None:
    """Platform superusers bypass optional MSP membership and location checks."""
    PerformerAssignmentService.ensure_can_modify_unit(
        user=UserFactory(is_staff=True, is_superuser=True),
        unit=WirelessUnitFactory(base_chassis__location=None),
    )
