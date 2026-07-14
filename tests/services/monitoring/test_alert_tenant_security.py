"""Tenant-scope contracts for alert recipients."""

from __future__ import annotations

from unittest.mock import patch

from django.test import override_settings

import pytest

from micboard.models.monitoring.alert import Alert
from micboard.services.monitoring.alert_delivery_service import AlertDeliveryService
from tests.factories.base import UserFactory
from tests.factories.hardware import WirelessChassisFactory, WirelessUnitFactory
from tests.factories.locations import BuildingFactory, LocationFactory
from tests.factories.monitoring import (
    MonitoringGroupFactory,
    MonitoringGroupLocationFactory,
    PerformerAssignmentFactory,
)
from tests.factories.multitenancy import OrganizationFactory, OrganizationMembershipFactory


@pytest.mark.django_db
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_alert_delivery_intersects_group_recipient_with_unit_tenant() -> None:
    """Group membership alone cannot send another tenant's device data by email."""
    recipient = UserFactory(email="recipient@example.test")
    recipient_organization = OrganizationFactory()
    device_organization = OrganizationFactory()
    OrganizationMembershipFactory(
        user=recipient,
        organization=recipient_organization,
        campus=None,
        role="viewer",
    )

    location = LocationFactory(
        building=BuildingFactory(organization_id=device_organization.pk),
    )
    chassis = WirelessChassisFactory(location=location, max_channels=1)
    channel = chassis.rf_channels.get(channel_number=1)
    unit = WirelessUnitFactory(
        base_chassis=chassis,
        assigned_resource=channel,
    )
    group = MonitoringGroupFactory()
    group.users.add(recipient)
    MonitoringGroupLocationFactory(monitoring_group=group, location=location)
    assignment = PerformerAssignmentFactory(
        wireless_unit=unit,
        monitoring_group=group,
    )
    with patch(
        "micboard.services.monitoring.alert_delivery_service.send_alert_email"
    ) as send_email:
        denied = AlertDeliveryService.create_alert(
            unit=unit,
            user=recipient,
            performer_assignment=assignment,
            alert_type="signal_loss",
            message="Tenant-private device signal",
        )

    assert denied is None
    assert not Alert.objects.exists()
    send_email.assert_not_called()

    OrganizationMembershipFactory(
        user=recipient,
        organization=device_organization,
        campus=None,
        role="viewer",
    )
    with patch(
        "micboard.services.monitoring.alert_delivery_service.send_alert_email",
        return_value=True,
    ) as send_email:
        allowed = AlertDeliveryService.create_alert(
            unit=unit,
            user=recipient,
            performer_assignment=assignment,
            alert_type="signal_loss",
            message="Tenant-private device signal",
        )

    assert allowed is not None
    send_email.assert_called_once_with(allowed, recipients=[recipient.email])


@pytest.mark.django_db
@pytest.mark.parametrize("revoked", ["user", "group"])
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_tenant_fanout_rejects_inactive_recipient_or_group(revoked: str) -> None:
    """Matching tenant membership cannot revive an inactive user or monitoring group."""
    recipient = UserFactory(email="recipient@example.test")
    organization = OrganizationFactory()
    OrganizationMembershipFactory(
        user=recipient,
        organization=organization,
        campus=None,
        role="viewer",
    )
    location = LocationFactory(building=BuildingFactory(organization_id=organization.pk))
    chassis = WirelessChassisFactory(location=location, max_channels=1)
    channel = chassis.rf_channels.get(channel_number=1)
    unit = WirelessUnitFactory(base_chassis=chassis, assigned_resource=channel)
    group = MonitoringGroupFactory()
    group.users.add(recipient)
    MonitoringGroupLocationFactory(monitoring_group=group, location=location)
    assignment = PerformerAssignmentFactory(wireless_unit=unit, monitoring_group=group)

    if revoked == "user":
        recipient.is_active = False
        recipient.save(update_fields=["is_active"])
    else:
        group.is_active = False
        group.save(update_fields=["is_active"])

    with patch(
        "micboard.services.monitoring.alert_delivery_service.send_alert_email"
    ) as send_email:
        denied = AlertDeliveryService.create_alert(
            unit=unit,
            user=recipient,
            performer_assignment=assignment,
            alert_type="signal_loss",
            message="Tenant-private signal",
        )

    assert denied is None
    assert not Alert.objects.exists()
    send_email.assert_not_called()
