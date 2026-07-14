"""Tenant-integrity contracts for performer assignments."""

from __future__ import annotations

from types import SimpleNamespace

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
