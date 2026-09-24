"""Branch coverage for the alert recipient scope predicate.

Every branch here decides whether a recipient is entitled to an alert, so each one is worth
pinning rather than inferring from the paths that happen to run in the round-trip tests.
"""

from __future__ import annotations

from typing import Any

from django.test import override_settings

import pytest

from micboard.services.monitoring.alert_fanout_service import AlertFanoutService
from tests.factories.base import UserFactory
from tests.factories.hardware import WirelessChassisFactory, WirelessUnitFactory
from tests.factories.locations import BuildingFactory, LocationFactory
from tests.factories.monitoring import (
    MonitoringGroupFactory,
    MonitoringGroupLocationFactory,
    PerformerAssignmentFactory,
)
from tests.factories.multitenancy import OrganizationFactory, OrganizationMembershipFactory

pytestmark = pytest.mark.django_db


def _scoped_unit(organization: Any) -> Any:
    """Build a saved unit whose chassis sits in one organization."""
    location = LocationFactory(building=BuildingFactory(organization_id=organization.pk))
    chassis = WirelessChassisFactory(location=location, max_channels=1)
    return WirelessUnitFactory(
        base_chassis=chassis,
        assigned_resource=chassis.rf_channels.get(channel_number=1),
    )


def test_an_unsaved_unit_has_no_scope() -> None:
    """A unit with no primary key cannot be intersected with anything, so it fails closed."""
    unit = WirelessUnitFactory.build()

    assert not AlertFanoutService.recipient_has_alert_scope(unit=unit, user=UserFactory())


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_a_unit_with_no_assigned_channel_is_scoped_by_the_unit_alone() -> None:
    """With no channel there is no second boundary to cross, so the unit's own is enough."""
    organization = OrganizationFactory()
    recipient = UserFactory()
    OrganizationMembershipFactory(
        user=recipient,
        organization=organization,
        campus=None,
        role="viewer",
    )
    unit = _scoped_unit(organization)
    unit.assigned_resource = None
    unit.save(update_fields=["assigned_resource"])
    group = MonitoringGroupFactory()
    group.users.add(recipient)
    MonitoringGroupLocationFactory(
        monitoring_group=group,
        location=unit.base_chassis.location,
    )

    assert AlertFanoutService.recipient_has_alert_scope(unit=unit, user=recipient)


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_a_current_assignment_is_still_refused_outside_the_unit_tenant() -> None:
    """Being the assigned, group-member recipient is not enough to cross a tenant boundary."""
    device_organization = OrganizationFactory()
    other_organization = OrganizationFactory()
    recipient = UserFactory()
    OrganizationMembershipFactory(
        user=recipient,
        organization=other_organization,
        campus=None,
        role="viewer",
    )
    unit = _scoped_unit(device_organization)
    group = MonitoringGroupFactory()
    group.users.add(recipient)
    MonitoringGroupLocationFactory(
        monitoring_group=group,
        location=unit.base_chassis.location,
    )
    assignment = PerformerAssignmentFactory(wireless_unit=unit, monitoring_group=group)

    assert (
        AlertFanoutService.current_authorized_recipient(
            unit=unit,
            assignment=assignment,
            user=recipient,
        )
        is None
    )
