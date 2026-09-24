"""An alert written for a recipient must be an alert that recipient can read.

Delivery authorizes the recipient against the wireless unit's tenant boundary, reached
through `base_chassis`. Reading authorizes against the alert row's own boundary, reached
through `channel__chassis`. Those are the same building for a unit assigned to a channel on
its own chassis, and different buildings as soon as it is not — so the two sides have to
agree on which boundary governs, or alerts land where nobody can read them.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from django.test import override_settings

import pytest

from micboard.models.monitoring.alert import Alert
from micboard.services.monitoring.alert_delivery_service import AlertDeliveryService
from micboard.services.monitoring.alerts import get_alerts_for_user
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


def _location_in(organization: Any) -> Any:
    """Build a location owned by one organization."""
    return LocationFactory(building=BuildingFactory(organization_id=organization.pk))


def _deliver(*, unit: Any, user: Any, assignment: Any) -> Alert | None:
    """Run delivery with email suppressed, returning whatever was persisted."""
    with patch(
        "micboard.services.monitoring.alert_delivery_service.email_service.send_alert_notification",
        return_value=True,
    ):
        return AlertDeliveryService.create_alert(
            unit=unit,
            user=user,
            performer_assignment=assignment,
            alert_type="signal_loss",
            message="Signal loss detected",
        )


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_a_delivered_alert_is_readable_by_the_recipient_it_was_written_for() -> None:
    """The ordinary case: unit and channel share a chassis, so both sides agree."""
    organization = OrganizationFactory()
    recipient = UserFactory(email="recipient@example.test")
    OrganizationMembershipFactory(
        user=recipient,
        organization=organization,
        campus=None,
        role="viewer",
    )
    location = _location_in(organization)
    chassis = WirelessChassisFactory(location=location, max_channels=1)
    channel = chassis.rf_channels.get(channel_number=1)
    unit = WirelessUnitFactory(base_chassis=chassis, assigned_resource=channel)
    group = MonitoringGroupFactory()
    group.users.add(recipient)
    MonitoringGroupLocationFactory(monitoring_group=group, location=location)
    assignment = PerformerAssignmentFactory(wireless_unit=unit, monitoring_group=group)

    alert = _deliver(unit=unit, user=recipient, assignment=assignment)

    assert alert is not None
    assert list(get_alerts_for_user(recipient)) == [alert]


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_delivery_authorizes_against_the_boundary_the_alert_will_land_in() -> None:
    """A unit assigned across a tenant boundary cannot produce an unreadable alert.

    The recipient administers the unit's organization but not the channel's. Delivery must
    refuse, because an alert attached to that channel would fall outside what the recipient
    is allowed to read.
    """
    unit_organization = OrganizationFactory()
    channel_organization = OrganizationFactory()
    recipient = UserFactory(email="recipient@example.test")
    OrganizationMembershipFactory(
        user=recipient,
        organization=unit_organization,
        campus=None,
        role="viewer",
    )
    unit_location = _location_in(unit_organization)
    channel_location = _location_in(channel_organization)
    unit_chassis = WirelessChassisFactory(location=unit_location, max_channels=1)
    foreign_chassis = WirelessChassisFactory(location=channel_location, max_channels=1)
    foreign_channel = foreign_chassis.rf_channels.get(channel_number=1)
    unit = WirelessUnitFactory(base_chassis=unit_chassis, assigned_resource=foreign_channel)
    group = MonitoringGroupFactory()
    group.users.add(recipient)
    MonitoringGroupLocationFactory(monitoring_group=group, location=unit_location)
    assignment = PerformerAssignmentFactory(wireless_unit=unit, monitoring_group=group)

    alert = _deliver(unit=unit, user=recipient, assignment=assignment)

    assert alert is None
    assert not Alert.objects.exists()


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_no_persisted_alert_is_invisible_to_its_own_recipient() -> None:
    """Whatever delivery persists, the read path admits — that is the shared invariant."""
    unit_organization = OrganizationFactory()
    channel_organization = OrganizationFactory()
    recipient = UserFactory(email="recipient@example.test")
    for organization in (unit_organization, channel_organization):
        OrganizationMembershipFactory(
            user=recipient,
            organization=organization,
            campus=None,
            role="viewer",
        )
    unit_location = _location_in(unit_organization)
    channel_location = _location_in(channel_organization)
    unit_chassis = WirelessChassisFactory(location=unit_location, max_channels=1)
    foreign_chassis = WirelessChassisFactory(location=channel_location, max_channels=1)
    foreign_channel = foreign_chassis.rf_channels.get(channel_number=1)
    unit = WirelessUnitFactory(base_chassis=unit_chassis, assigned_resource=foreign_channel)
    group = MonitoringGroupFactory()
    group.users.add(recipient)
    MonitoringGroupLocationFactory(monitoring_group=group, location=unit_location)
    MonitoringGroupLocationFactory(monitoring_group=group, location=channel_location)
    assignment = PerformerAssignmentFactory(wireless_unit=unit, monitoring_group=group)

    alert = _deliver(unit=unit, user=recipient, assignment=assignment)

    # A recipient holding both organizations is entitled to this alert, so delivery must
    # produce one — guarding the read assertion behind `if alert` would let the test pass
    # without ever exercising the read path.
    assert alert is not None
    assert list(get_alerts_for_user(recipient)) == [alert]
