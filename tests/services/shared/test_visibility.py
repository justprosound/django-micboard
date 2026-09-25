"""One rule for "which rows may this user see", exercised through `visible_to`.

Visibility is the tenant boundary intersected with monitoring reach. These tests build one
small inventory and ask the same question for every deployment mode and kind of user, so a
model that answers differently from its neighbours shows up here.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.db import router
from django.test import override_settings

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.locations.structure import Building, Location
from micboard.models.monitoring.group import MonitoringGroup
from micboard.models.monitoring.performer import Performer
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.models.rf_coordination.rf_channel import RFChannel
from micboard.multitenancy.models import Organization, OrganizationMembership
from micboard.services.shared.tenant_principal import TenantPrincipal
from micboard.services.shared.visibility import reaches, restrict_to_tenant_boundary, visible_to

ANONYMOUS = SimpleNamespace(is_authenticated=False, is_superuser=False, pk=None)


@dataclass
class Inventory:
    """Two tenants, one monitoring group, and hardware inside and outside its reach."""

    group: MonitoringGroup
    building: Building
    foreign_building: Building
    grouped_location: Location
    grouped_chassis: WirelessChassis
    ungrouped_chassis: WirelessChassis
    foreign_chassis: WirelessChassis
    grouped_unit: WirelessUnit
    channel_reached_unit: WirelessUnit
    foreign_unit: WirelessUnit
    linked_channel: RFChannel
    assigned_performer: Performer
    unassigned_performer: Performer
    viewer: Any
    admin: Any
    restricted_superuser: Any
    outsider: Any


def _user(username: str, **extra: Any) -> Any:
    return get_user_model().objects.create_user(username=username, **extra)


@pytest.fixture
def inventory(db: None) -> Inventory:
    home = Organization.objects.create(name="Home", slug="home")
    foreign = Organization.objects.create(name="Foreign", slug="foreign")
    manufacturer = Manufacturer.objects.create(name="Vendor", code="visibility-vendor")
    group = MonitoringGroup.objects.create(name="Stage crew")

    building = Building.objects.create(name="Home hall", organization_id=home.pk)
    foreign_building = Building.objects.create(name="Foreign hall", organization_id=foreign.pk)
    grouped_location = Location.objects.create(building=building, name="Stage")
    ungrouped_location = Location.objects.create(building=building, name="Lobby")
    foreign_location = Location.objects.create(building=foreign_building, name="Foreign stage")
    # A group that also covers another tenant's location must not widen that tenant.
    group.locations.add(grouped_location, foreign_location)

    def chassis(name: str, location: Location, octet: int) -> WirelessChassis:
        return WirelessChassis.objects.create(
            name=name,
            manufacturer=manufacturer,
            api_device_id=name,
            role="receiver",
            ip=f"192.0.2.{octet}",
            location=location,
        )

    grouped_chassis = chassis("grouped", grouped_location, 1)
    ungrouped_chassis = chassis("ungrouped", ungrouped_location, 2)
    foreign_chassis = chassis("foreign", foreign_location, 3)
    linked_channel = ungrouped_chassis.rf_channels.order_by("channel_number").first()
    assert linked_channel is not None
    group.channels.add(linked_channel)

    def unit(base: WirelessChassis, slot: int, channel: RFChannel | None = None) -> WirelessUnit:
        return WirelessUnit.objects.create(
            base_chassis=base,
            manufacturer=manufacturer,
            slot=slot,
            assigned_resource=channel,
        )

    grouped_unit = unit(grouped_chassis, 1)
    channel_reached_unit = unit(ungrouped_chassis, 2, linked_channel)
    foreign_unit = unit(foreign_chassis, 3)

    assigned_performer = Performer.objects.create(name="Assigned")
    unassigned_performer = Performer.objects.create(name="Unassigned")
    PerformerAssignment.objects.create(
        performer=assigned_performer,
        wireless_unit=grouped_unit,
        monitoring_group=group,
    )

    viewer = _user("viewer")
    admin = _user("admin")
    restricted_superuser = _user("restricted-superuser", is_superuser=True, is_staff=True)
    outsider = _user("outsider")
    group.users.add(viewer)
    OrganizationMembership.objects.create(user=viewer, organization=home, role="viewer")
    OrganizationMembership.objects.create(user=admin, organization=home, role="admin")
    OrganizationMembership.objects.create(
        user=restricted_superuser, organization=home, role="viewer"
    )

    return Inventory(
        group=group,
        building=building,
        foreign_building=foreign_building,
        grouped_location=grouped_location,
        grouped_chassis=grouped_chassis,
        ungrouped_chassis=ungrouped_chassis,
        foreign_chassis=foreign_chassis,
        grouped_unit=grouped_unit,
        channel_reached_unit=channel_reached_unit,
        foreign_unit=foreign_unit,
        linked_channel=linked_channel,
        assigned_performer=assigned_performer,
        unassigned_performer=unassigned_performer,
        viewer=viewer,
        admin=admin,
        restricted_superuser=restricted_superuser,
        outsider=outsider,
    )


def _pks(model: type[Any], user: Any) -> set[int]:
    return set(visible_to(model, user=user).values_list("pk", flat=True))


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_msp_viewer_sees_only_what_their_groups_reach_inside_their_tenant(
    inventory: Inventory,
) -> None:
    """Viewers are narrowed to monitoring reach, and reach never crosses the tenant."""
    user = inventory.viewer

    assert _pks(WirelessChassis, user) == {inventory.grouped_chassis.pk}
    assert _pks(WirelessUnit, user) == {
        inventory.grouped_unit.pk,
        inventory.channel_reached_unit.pk,
    }
    assert _pks(RFChannel, user) == {
        *inventory.grouped_chassis.rf_channels.values_list("pk", flat=True),
        inventory.linked_channel.pk,
    }
    assert _pks(Building, user) == {inventory.building.pk}
    assert _pks(Location, user) == {inventory.grouped_location.pk}
    assert _pks(Performer, user) == {inventory.assigned_performer.pk}
    assert _pks(MonitoringGroup, user) == {inventory.group.pk}


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
@pytest.mark.parametrize("user_attribute", ["admin", "restricted_superuser"])
def test_msp_administrators_and_restricted_superusers_see_their_whole_tenant(
    inventory: Inventory,
    user_attribute: str,
) -> None:
    """Administration is tenant-wide; monitoring groups do not narrow it."""
    user = getattr(inventory, user_attribute)

    assert _pks(WirelessChassis, user) == {
        inventory.grouped_chassis.pk,
        inventory.ungrouped_chassis.pk,
    }
    assert _pks(WirelessUnit, user) == {
        inventory.grouped_unit.pk,
        inventory.channel_reached_unit.pk,
    }
    assert _pks(Building, user) == {inventory.building.pk}


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_msp_user_without_membership_sees_nothing(inventory: Inventory) -> None:
    """No active membership means no tenant, whatever monitoring groups say."""
    inventory.group.users.add(inventory.outsider)

    for model in (WirelessChassis, WirelessUnit, RFChannel, Building, Performer):
        assert _pks(model, inventory.outsider) == set()


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_restricted_superuser_sees_only_monitoring_groups_it_belongs_to(
    inventory: Inventory,
) -> None:
    """The monitoring-group API cannot list every group to a tenant-limited superuser."""
    assert _pks(MonitoringGroup, inventory.restricted_superuser) == set()


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=True)
def test_cross_org_superuser_sees_every_tenant_and_only_active_groups(
    inventory: Inventory,
) -> None:
    inactive = MonitoringGroup.objects.create(name="Retired", is_active=False)
    user = inventory.restricted_superuser

    assert inventory.foreign_chassis.pk in _pks(WirelessChassis, user)
    assert inactive.pk not in _pks(MonitoringGroup, user)
    assert inventory.group.pk in _pks(MonitoringGroup, user)


def test_single_site_user_sees_monitoring_reach_without_a_tenant_boundary(
    inventory: Inventory,
) -> None:
    user = inventory.viewer

    assert _pks(WirelessChassis, user) == {
        inventory.grouped_chassis.pk,
        inventory.foreign_chassis.pk,
    }
    assert _pks(WirelessUnit, user) == {
        inventory.grouped_unit.pk,
        inventory.channel_reached_unit.pk,
        inventory.foreign_unit.pk,
    }
    assert _pks(Performer, user) == {
        inventory.assigned_performer.pk,
        inventory.unassigned_performer.pk,
    }


@override_settings(MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_single_site_superuser_sees_everything(inventory: Inventory) -> None:
    """Single-site has no organization boundary for the cross-organization switch to guard."""
    user = inventory.restricted_superuser

    assert _pks(WirelessChassis, user) == set(WirelessChassis.objects.values_list("pk", flat=True))
    assert _pks(WirelessUnit, user) == set(WirelessUnit.objects.values_list("pk", flat=True))


@override_settings(MICBOARD_MULTI_SITE_MODE=True, SITE_ID=1)
def test_multi_site_user_sees_monitoring_reach_inside_the_current_site(
    inventory: Inventory,
) -> None:
    current, _created = Site.objects.get_or_create(pk=1, defaults={"domain": "a.test"})
    other = Site.objects.create(domain="b.test", name="b")
    Building.objects.filter(pk=inventory.building.pk).update(site=current)
    Building.objects.filter(pk=inventory.foreign_building.pk).update(site=other)

    assert _pks(WirelessChassis, inventory.viewer) == {inventory.grouped_chassis.pk}


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_tenant_boundary_ignores_monitoring_reach(inventory: Inventory) -> None:
    """The admin boundary shows a viewer their whole tenant and nothing outside it."""
    chassis = restrict_to_tenant_boundary(WirelessChassis.objects.all(), user=inventory.viewer)

    assert set(chassis.values_list("pk", flat=True)) == {
        inventory.grouped_chassis.pk,
        inventory.ungrouped_chassis.pk,
    }


def test_group_reach_is_answered_by_the_same_declarations(inventory: Inventory) -> None:
    """Assignment checks and visibility agree on what a group covers."""
    assert reaches(inventory.group, inventory.grouped_unit)
    assert reaches(inventory.group, inventory.channel_reached_unit)
    assert not reaches(MonitoringGroup.objects.create(name="Empty"), inventory.grouped_unit)


@pytest.mark.django_db
def test_inactive_and_anonymous_users_see_nothing() -> None:
    inactive = _user("inactive", is_active=False)
    for user in (ANONYMOUS, inactive):
        for model in (WirelessChassis, Building, MonitoringGroup):
            assert visible_to(model, user=user).query.is_empty()


@pytest.mark.parametrize("using", ["replica", None])
def test_the_principal_is_resolved_on_the_database_being_asked_about(
    using: str | None,
) -> None:
    """A multi-database host must not narrow one database's rows by another's memberships."""
    expected = using or router.db_for_read(WirelessChassis)
    with patch.object(
        TenantPrincipal,
        "resolve",
        wraps=TenantPrincipal.resolve,
    ) as resolve:
        result = visible_to(WirelessChassis, user=ANONYMOUS, using=using)

    assert resolve.call_args.kwargs["using"] == expected
    assert result.db == expected


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_msp_fails_closed_without_the_multitenancy_app(inventory: Inventory) -> None:
    """Memberships cannot be read, so a restricted user holds no tenant."""
    with patch(
        "micboard.services.shared.tenant_principal.apps.is_installed",
        return_value=False,
    ):
        assert _pks(WirelessChassis, inventory.admin) == set()
