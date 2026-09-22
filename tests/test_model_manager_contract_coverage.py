"""Tenant visibility contracts on the model querysets.

`for_user` is the only queryset helper the application calls, and it is the one that has to
fail closed. These cover the base cascade and each model-specific override of it.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import override_settings

from micboard.models.base_managers import TenantOptimizedQuerySet
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import (
    PerformerAssignment,
    PerformerAssignmentQuerySet,
)
from micboard.models.rf_coordination.rf_channel import RFChannel, RFChannelQuerySet
from micboard.models.settings.registry import Setting

ANONYMOUS = SimpleNamespace(is_authenticated=False, is_superuser=False)


def test_every_visibility_override_fails_closed_for_an_anonymous_user() -> None:
    """No model widens access to a request without an authenticated user."""
    for manager in (
        WirelessUnit.objects,
        Performer.objects,
        PerformerAssignment.objects,
        RFChannel.objects,
        WirelessChassis.objects,
    ):
        assert manager.for_user(user=ANONYMOUS).query.is_empty()


@override_settings(MICBOARD_MSP_ENABLED=True)
def test_membership_scope_fails_closed_without_an_ownership_path() -> None:
    """A model with no declared tenant ownership cannot be scoped by membership."""
    setting_queryset = TenantOptimizedQuerySet(Setting, using="default")

    assert setting_queryset.for_memberships([(1, 2)]).query.is_empty()
    assert setting_queryset.for_memberships([]).query.is_empty()


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_msp_visibility_requires_its_ownership_application() -> None:
    """MSP mode fails closed if its ownership application is unavailable."""
    user = SimpleNamespace(is_authenticated=True, is_superuser=False)
    queryset = TenantOptimizedQuerySet(WirelessChassis, using="default")

    with patch("micboard.models.base_managers.apps.is_installed", return_value=False):
        assert queryset.for_user(user=user).query.is_empty()


def test_rf_channel_visibility_includes_building_wide_monitoring_scopes() -> None:
    """A group that includes all rooms sees every channel in that building."""
    locations = Mock()
    locations.values_list.return_value = [1]
    buildings = Mock()
    buildings.values_list.return_value = [2]
    groups = Mock()
    groups.filter.side_effect = [locations, buildings]
    user = SimpleNamespace(is_authenticated=True, is_superuser=False, monitoring_groups=groups)

    query = RFChannel.objects.for_user(user=user)

    assert "building_id" in str(query.query)


def test_a_superuser_keeps_the_typed_queryset_on_every_override() -> None:
    """Visibility helpers stay composable, so callers can keep filtering the result."""
    superuser = SimpleNamespace(is_authenticated=True, is_superuser=True)

    assert isinstance(RFChannel.objects.for_user(user=superuser), RFChannelQuerySet)
    assert isinstance(
        PerformerAssignment.objects.for_user(user=superuser),
        PerformerAssignmentQuerySet,
    )


def test_active_assignments_exclude_inactive_rows() -> None:
    """Receiver browsing annotates visible assignments, and only active ones count."""
    query = str(PerformerAssignment.objects.active().query)

    assert "is_active" in query
