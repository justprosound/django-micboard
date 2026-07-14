"""Selected chassis refresh service regressions."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import Permission
from django.db import connection
from django.test import override_settings
from django.utils import timezone

import pytest

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.hardware.chassis_refresh_service import (
    MAX_CHASSIS_REFRESH_BATCH,
    ChassisRefreshService,
)
from micboard.services.manufacturer.plugin_registry import PluginRegistry
from tests.factories.base import UserFactory
from tests.factories.hardware import WirelessChassisFactory
from tests.factories.locations import BuildingFactory, LocationFactory
from tests.factories.multitenancy import OrganizationFactory, OrganizationMembershipFactory

pytestmark = pytest.mark.django_db


class _Plugin:
    requested_ids: list[str] = []
    observed_atomic_blocks: list[bool] = []

    def __init__(self, manufacturer: Any) -> None:
        self.manufacturer = manufacturer

    def get_device(self, device_id: str) -> dict[str, str] | None:
        self.requested_ids.append(device_id)
        self.observed_atomic_blocks.append(connection.in_atomic_block)
        if device_id == "missing-device":
            return None
        return {"id": device_id}

    def transform_device_data(self, device_data: dict[str, str]) -> dict[str, str]:
        return {"name": f"Refreshed {device_data['id']}", "firmware": "9.8.7"}


def test_refresh_persists_details_and_online_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """A responding selected chassis persists details and a valid online transition."""
    chassis = WirelessChassisFactory(status="offline")
    monkeypatch.setattr(PluginRegistry, "get_plugin_class", staticmethod(lambda _code: _Plugin))

    result = ChassisRefreshService.refresh(queryset=WirelessChassis.objects.filter(pk=chassis.pk))

    chassis.refresh_from_db()
    assert result.synced_count == 1
    assert result.failed_count == 0
    assert chassis.name == f"Refreshed {chassis.api_device_id}"
    assert chassis.firmware_version == "9.8.7"
    assert chassis.status == "online"
    assert chassis.last_seen <= timezone.now()


@pytest.mark.django_db(transaction=True)
def test_refresh_does_not_hold_database_transaction_during_network_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slow manufacturer I/O happens before the short persistence transaction."""
    chassis = WirelessChassisFactory(status="offline")
    monkeypatch.setattr(PluginRegistry, "get_plugin_class", staticmethod(lambda _code: _Plugin))
    _Plugin.observed_atomic_blocks = []

    ChassisRefreshService.refresh_ids(chassis_ids=[chassis.pk])

    assert _Plugin.observed_atomic_blocks == [False]


def test_refresh_never_widens_selected_queryset(monkeypatch: pytest.MonkeyPatch) -> None:
    """A shared manufacturer must not turn one selected row into a global poll."""
    selected = WirelessChassisFactory(status="online")
    unselected = WirelessChassisFactory(manufacturer=selected.manufacturer, status="online")
    monkeypatch.setattr(PluginRegistry, "get_plugin_class", staticmethod(lambda _code: _Plugin))
    _Plugin.requested_ids = []

    result = ChassisRefreshService.refresh(queryset=WirelessChassis.objects.filter(pk=selected.pk))

    assert result.synced_count == 1
    assert _Plugin.requested_ids == [selected.api_device_id]
    unselected.refresh_from_db()
    assert not unselected.name.startswith("Refreshed")


def test_refresh_reports_missing_device_without_mutation(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing API device is reported and leaves the selected row unchanged."""
    chassis = WirelessChassisFactory(api_device_id="missing-device", status="offline")
    original_name = chassis.name
    monkeypatch.setattr(PluginRegistry, "get_plugin_class", staticmethod(lambda _code: _Plugin))

    result = ChassisRefreshService.refresh(queryset=WirelessChassis.objects.filter(pk=chassis.pk))

    chassis.refresh_from_db()
    assert result.synced_count == 0
    assert result.failed_count == 1
    assert chassis.name == original_name
    assert chassis.status == "offline"


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_queued_refresh_rechecks_actor_tenant_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    """A queued selection cannot refresh a chassis outside the actor's current tenant."""
    allowed_organization = OrganizationFactory()
    foreign_organization = OrganizationFactory()
    actor = UserFactory(is_active=True, is_staff=True, is_superuser=False)
    actor.user_permissions.add(Permission.objects.get(codename="change_wirelesschassis"))
    OrganizationMembershipFactory(
        user=actor,
        organization=allowed_organization,
        campus=None,
    )
    allowed = WirelessChassisFactory(
        status="offline",
        location=LocationFactory(building=BuildingFactory(organization_id=allowed_organization.pk)),
    )
    foreign = WirelessChassisFactory(
        status="offline",
        location=LocationFactory(building=BuildingFactory(organization_id=foreign_organization.pk)),
    )
    monkeypatch.setattr(PluginRegistry, "get_plugin_class", staticmethod(lambda _code: _Plugin))
    _Plugin.requested_ids = []

    result = ChassisRefreshService.refresh_authorized_ids(
        chassis_ids=[allowed.pk, foreign.pk],
        actor_id=actor.pk,
    )

    assert result.synced_count == 1
    assert result.failed_count == 1
    assert result.denied is False
    assert _Plugin.requested_ids == [allowed.api_device_id]


def test_queued_refresh_rejects_deactivated_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deactivation after enqueue prevents transport and persistence work."""
    actor = UserFactory(is_active=False, is_staff=True, is_superuser=True)
    chassis = WirelessChassisFactory(status="offline")
    monkeypatch.setattr(PluginRegistry, "get_plugin_class", staticmethod(lambda _code: _Plugin))
    _Plugin.requested_ids = []

    result = ChassisRefreshService.refresh_authorized_ids(
        chassis_ids=[chassis.pk],
        actor_id=actor.pk,
    )

    assert result.denied is True
    assert result.failed_count == 1
    assert _Plugin.requested_ids == []


def test_queued_refresh_bounds_arbitrary_id_iterables() -> None:
    """A malformed task payload cannot drive unbounded queryset construction."""
    actor = UserFactory(is_active=True, is_staff=True, is_superuser=True)
    consumed = 0

    def chassis_ids():
        nonlocal consumed
        for identifier in range(1, MAX_CHASSIS_REFRESH_BATCH + 3):
            consumed += 1
            yield identifier

    result = ChassisRefreshService.refresh_authorized_ids(
        chassis_ids=chassis_ids(),
        actor_id=actor.pk,
    )

    assert consumed == MAX_CHASSIS_REFRESH_BATCH + 1
    assert result.truncated is True
    assert result.synced_count == 0
