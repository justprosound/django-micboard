"""Typed queryset and manager delegation contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import override_settings

from micboard.models.base_managers import TenantOptimizedManager, TenantOptimizedQuerySet
from micboard.models.hardware.charger import Charger, ChargerQuerySet
from micboard.models.hardware.display_wall import DisplayWall, DisplayWallQuerySet, WallSection
from micboard.models.hardware.wireless_chassis import WirelessChassis, WirelessChassisQuerySet
from micboard.models.hardware.wireless_unit import WirelessUnit, WirelessUnitQuerySet
from micboard.models.integrations import ManufacturerAPIServer
from micboard.models.monitoring.group import MonitoringGroup
from micboard.models.monitoring.performer import Performer, PerformerQuerySet
from micboard.models.monitoring.performer_assignment import (
    PerformerAssignment,
    PerformerAssignmentQuerySet,
)
from micboard.models.rf_coordination.rf_channel import RFChannel, RFChannelQuerySet
from micboard.models.settings.registry import Setting


def test_hardware_managers_expose_domain_querysets_and_filters() -> None:
    """Public hardware manager helpers retain typed, composable querysets."""
    charger_queries = (
        Charger.objects.by_location(location_id=3),
        Charger.objects.active(),
        Charger.objects.with_inventory(),
    )
    assert all(isinstance(queryset, ChargerQuerySet) for queryset in charger_queries)
    assert Charger.objects.with_inventory()._prefetch_related_lookups == ("slots",)

    wall_queries = (
        DisplayWall.objects.active(),
        DisplayWall.objects.by_location(location_id=3),
    )
    assert all(isinstance(queryset, DisplayWallQuerySet) for queryset in wall_queries)
    assert DisplayWall.objects.get_queryset().with_sections()._prefetch_related_lookups == (
        "sections",
    )

    section_queryset = WallSection.objects.all()
    assert "wall_id" in str(section_queryset.by_wall(wall_id=2).query)
    assert "is_active" in str(section_queryset.active().query)
    assert section_queryset.with_chargers()._prefetch_related_lookups == ("chargers",)


def test_chassis_manager_filters_both_manufacturer_identity_forms() -> None:
    """Chassis callers may filter by stable vendor code or database identifier."""
    queries = (
        WirelessChassis.objects.active(),
        WirelessChassis.objects.inactive(),
        WirelessChassis.objects.by_status(status="online"),
        WirelessChassis.objects.by_role(role="receiver"),
        WirelessChassis.objects.by_manufacturer(manufacturer="shure"),
        WirelessChassis.objects.by_manufacturer(manufacturer=7),
        WirelessChassis.objects.with_channels(),
    )
    assert all(isinstance(queryset, WirelessChassisQuerySet) for queryset in queries)
    assert queries[-1]._prefetch_related_lookups == ("rf_channels",)


def test_wireless_unit_manager_and_user_short_circuits() -> None:
    """Unit manager helpers compose, while anonymous users remain fail-closed."""
    queries = (
        WirelessUnit.objects.active(),
        WirelessUnit.objects.by_status(status="online"),
        WirelessUnit.objects.by_type(device_type="transceiver"),
        WirelessUnit.objects.low_battery(threshold=15),
    )
    assert all(isinstance(queryset, WirelessUnitQuerySet) for queryset in queries)

    anonymous = SimpleNamespace(is_authenticated=False, is_superuser=False)
    assert WirelessUnit.objects.for_user(user=anonymous).query.is_empty()


def test_performer_and_assignment_managers_cover_public_helpers() -> None:
    """Performer-domain managers preserve visibility, eager-load, and alert helpers."""
    anonymous = SimpleNamespace(is_authenticated=False, is_superuser=False)
    assert Performer.objects.for_user(user=anonymous).query.is_empty()
    assert PerformerAssignment.objects.for_user(user=anonymous).query.is_empty()

    assert isinstance(Performer.objects.active(), PerformerQuerySet)
    assert Performer.objects.with_assignments()._prefetch_related_lookups == (
        "assignments",
        "assignments__wireless_unit",
    )
    assert "monitoring_group" in str(
        Performer.objects.get_queryset().by_monitoring_group(group=MonitoringGroup(pk=4)).query
    )

    assignments = PerformerAssignment.objects.get_queryset()
    assert isinstance(PerformerAssignment.objects.active(), PerformerAssignmentQuerySet)
    assert isinstance(
        PerformerAssignment.objects.by_monitoring_group(group=MonitoringGroup(pk=4)),
        PerformerAssignmentQuerySet,
    )
    assert assignments.with_performer_and_unit().query.select_related
    assert str(assignments.needing_alerts().query).count('"updated_at"') == 1
    after = datetime(2026, 1, 1, tzinfo=UTC)
    assert str(assignments.needing_alerts(after=after).query).count('"updated_at"') == 2


def test_rf_channel_manager_helpers_and_expanded_room_visibility() -> None:
    """RF channel helpers compose and include building-wide monitoring scopes."""
    queries = (
        RFChannel.objects.by_direction(direction="receive"),
        RFChannel.objects.receive_links(),
        RFChannel.objects.send_links(),
        RFChannel.objects.with_chassis(),
        RFChannel.objects.with_wireless_unit(),
    )
    assert all(isinstance(queryset, RFChannelQuerySet) for queryset in queries)
    assert queries[-1]._prefetch_related_lookups == ("active_wireless_unit",)

    anonymous = SimpleNamespace(is_authenticated=False, is_superuser=False)
    superuser = SimpleNamespace(is_authenticated=True, is_superuser=True)
    assert RFChannel.objects.for_user(user=anonymous).query.is_empty()
    assert isinstance(RFChannel.objects.for_user(user=superuser), RFChannelQuerySet)

    locations = Mock()
    locations.values_list.return_value = [1]
    buildings = Mock()
    buildings.values_list.return_value = [2]
    groups = Mock()
    groups.filter.side_effect = [locations, buildings]
    user = SimpleNamespace(is_authenticated=True, is_superuser=False, monitoring_groups=groups)
    query = RFChannel.objects.for_user(user=user)
    assert "building_id" in str(query.query)


@override_settings(MICBOARD_MSP_ENABLED=True)
def test_base_tenant_filters_fail_closed_without_ownership_paths() -> None:
    """Models without declared ownership never widen organization or campus access."""
    queryset = TenantOptimizedQuerySet(ManufacturerAPIServer, using="default")
    assert queryset.for_organization(organization=9).query.is_empty()
    assert queryset.for_campus(campus_id=9).query.is_empty()

    setting_queryset = TenantOptimizedQuerySet(Setting, using="default")
    assert setting_queryset.for_memberships([(1, 2)]).query.is_empty()
    assert setting_queryset.for_memberships([]).query.is_empty()


def test_base_optimization_helpers_cover_present_and_absent_relations() -> None:
    """Shared eager-loading helpers only add relations supported by their model."""
    chassis = TenantOptimizedQuerySet(WirelessChassis, using="default")
    assert chassis.with_manufacturer().query.select_related
    assert chassis.with_location().query.select_related
    assert "last_seen" in str(chassis.recently_seen(minutes=5).query)

    channel = TenantOptimizedQuerySet(RFChannel, using="default")
    assert channel.with_chassis().query.select_related

    unrelated = TenantOptimizedQuerySet(Setting, using="default")
    assert unrelated.with_manufacturer() is unrelated
    assert unrelated.with_location() is unrelated
    assert unrelated.with_chassis() is unrelated
    assert unrelated.recently_seen() is unrelated

    assert WirelessChassis.objects.with_manufacturer().query.select_related
    assert WirelessChassis.objects.with_location().query.select_related
    assert "last_seen" in str(WirelessChassis.objects.recently_seen(minutes=5).query)

    manager = TenantOptimizedManager()
    manager.model = ManufacturerAPIServer
    assert isinstance(manager.get_queryset(), TenantOptimizedQuerySet)


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_base_user_filter_requires_multitenancy_app() -> None:
    """MSP mode fails closed if its ownership application is unavailable."""
    user = SimpleNamespace(is_authenticated=True, is_superuser=False)
    queryset = TenantOptimizedQuerySet(WirelessChassis, using="default")
    with patch("micboard.models.base_managers.apps.is_installed", return_value=False):
        assert queryset.for_user(user=user).query.is_empty()
