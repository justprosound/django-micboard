"""Factories for performers, monitoring groups, assignments, and alerts."""

from __future__ import annotations

import factory

from micboard.models.monitoring.alert import Alert, UserAlertPreference
from micboard.models.monitoring.group import MonitoringGroup, MonitoringGroupLocation
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment

from .base import ProjectModelFactory
from .registry import register_factory


@register_factory("micboard.Performer")
class PerformerFactory(ProjectModelFactory):
    """Create a performer with deterministic contact data."""

    class Meta:
        model = Performer

    name = factory.Sequence(lambda number: f"Performer {number}")
    email = factory.Sequence(lambda number: f"performer-{number}@example.test")


@register_factory("micboard.MonitoringGroup")
class MonitoringGroupFactory(ProjectModelFactory):
    """Create a uniquely named monitoring group."""

    class Meta:
        model = MonitoringGroup

    name = factory.Sequence(lambda number: f"Monitoring Group {number}")


@register_factory("micboard.MonitoringGroupLocation")
class MonitoringGroupLocationFactory(ProjectModelFactory):
    """Create an explicit monitoring-group-to-location assignment."""

    class Meta:
        model = MonitoringGroupLocation

    monitoring_group = factory.SubFactory("tests.factories.monitoring.MonitoringGroupFactory")
    location = factory.SubFactory("tests.factories.locations.LocationFactory")


@register_factory("micboard.PerformerAssignment")
class PerformerAssignmentFactory(ProjectModelFactory):
    """Create a performer, unit, and monitoring-group assignment graph."""

    class Meta:
        model = PerformerAssignment

    performer = factory.SubFactory("tests.factories.monitoring.PerformerFactory")
    wireless_unit = factory.SubFactory("tests.factories.hardware.WirelessUnitFactory")
    monitoring_group = factory.SubFactory("tests.factories.monitoring.MonitoringGroupFactory")


@register_factory("micboard.UserAlertPreference")
class UserAlertPreferenceFactory(ProjectModelFactory):
    """Create alert preferences for a host-project user."""

    class Meta:
        model = UserAlertPreference

    user = factory.SubFactory("tests.factories.base.UserFactory")
    email_address = factory.LazyAttribute(lambda preference: preference.user.email)


@register_factory("micboard.Alert")
class AlertFactory(ProjectModelFactory):
    """Create a pending battery alert for a channel and user."""

    class Meta:
        model = Alert

    channel = factory.SubFactory("tests.factories.rf_coordination.RFChannelFactory")
    user = factory.SubFactory("tests.factories.base.UserFactory")
    alert_type = "battery_low"
    message = factory.Sequence(lambda number: f"Factory alert {number}")
