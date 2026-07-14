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


class _EmptyTransformPlugin(_Plugin):
    def transform_device_data(self, device_data: dict[str, str]) -> dict[str, str]:
        return {}


class _SelectiveFailurePlugin(_Plugin):
    private_detail = "private transport details"

    def get_device(self, device_id: str) -> dict[str, str] | None:
        if device_id == "raise-device":
            raise RuntimeError(self.private_detail)
        return super().get_device(device_id)


class _NameOnlyPlugin(_Plugin):
    def transform_device_data(self, device_data: dict[str, str]) -> dict[str, str]:
        return {"name": "Name-only refresh"}


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

    ChassisRefreshService.refresh(queryset=WirelessChassis.objects.filter(pk=chassis.pk))

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


def test_refresh_reports_untransformable_device_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plugin that cannot normalize its response cannot partially update a row."""
    chassis = WirelessChassisFactory(status="offline")
    original_name = chassis.name
    monkeypatch.setattr(
        PluginRegistry,
        "get_plugin_class",
        staticmethod(lambda _code: _EmptyTransformPlugin),
    )

    result = ChassisRefreshService.refresh(queryset=WirelessChassis.objects.filter(pk=chassis.pk))

    chassis.refresh_from_db()
    assert result.synced_count == 0
    assert result.failed_count == 1
    assert chassis.name == original_name
    assert chassis.status == "offline"


def test_refresh_contains_one_transport_failure_and_continues_siblings(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One vendor failure is redacted and cannot abort the remaining selection."""
    failed = WirelessChassisFactory(api_device_id="raise-device", status="offline")
    refreshed = WirelessChassisFactory(
        manufacturer=failed.manufacturer,
        api_device_id="healthy-device",
        status="offline",
    )
    monkeypatch.setattr(
        PluginRegistry,
        "get_plugin_class",
        staticmethod(lambda _code: _SelectiveFailurePlugin),
    )

    result = ChassisRefreshService.refresh(
        queryset=WirelessChassis.objects.filter(pk__in=[failed.pk, refreshed.pk])
    )

    refreshed.refresh_from_db()
    assert result.synced_count == 1
    assert result.failed_count == 1
    assert refreshed.status == "online"
    assert "private transport details" not in caplog.text
    assert "error details redacted" in caplog.text


@pytest.mark.parametrize("initial_status", ["discovered", "retired"])
def test_refresh_preserves_lifecycle_contract_without_missing_firmware(
    monkeypatch: pytest.MonkeyPatch,
    initial_status: str,
) -> None:
    """Discovered devices transition legally while retired devices stay retired."""
    chassis = WirelessChassisFactory(status=initial_status, firmware_version="1.0.0")
    monkeypatch.setattr(
        PluginRegistry,
        "get_plugin_class",
        staticmethod(lambda _code: _NameOnlyPlugin),
    )

    result = ChassisRefreshService.refresh(queryset=WirelessChassis.objects.filter(pk=chassis.pk))

    chassis.refresh_from_db()
    assert result.synced_count == 1
    assert chassis.firmware_version == "1.0.0"
    assert chassis.name == "Name-only refresh"
    assert chassis.status == ("online" if initial_status == "discovered" else "retired")


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
        role="admin",
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


@pytest.mark.parametrize("downgraded_role", ["viewer", "operator"])
@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_ALLOW_CROSS_ORG_VIEW=False)
def test_queued_refresh_rejects_tenant_role_downgrade(
    monkeypatch: pytest.MonkeyPatch,
    downgraded_role: str,
) -> None:
    """A role downgrade after enqueue prevents delayed manufacturer API access."""
    organization = OrganizationFactory()
    actor = UserFactory(is_active=True, is_staff=True, is_superuser=False)
    actor.user_permissions.add(Permission.objects.get(codename="change_wirelesschassis"))
    membership = OrganizationMembershipFactory(
        user=actor,
        organization=organization,
        campus=None,
        role="admin",
    )
    chassis = WirelessChassisFactory(
        status="offline",
        location=LocationFactory(building=BuildingFactory(organization_id=organization.pk)),
    )
    membership.role = downgraded_role
    membership.save(update_fields=["role"])
    monkeypatch.setattr(PluginRegistry, "get_plugin_class", staticmethod(lambda _code: _Plugin))
    _Plugin.requested_ids = []

    result = ChassisRefreshService.refresh_authorized_ids(
        chassis_ids=[chassis.pk],
        actor_id=actor.pk,
    )

    assert result.denied is True
    assert result.synced_count == 0
    assert result.failed_count == 1
    assert _Plugin.requested_ids == []


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


@pytest.mark.parametrize(
    ("is_staff", "grant_permission"),
    [(False, True), (True, False)],
)
def test_queued_refresh_requires_staff_and_django_permission(
    monkeypatch: pytest.MonkeyPatch,
    *,
    is_staff: bool,
    grant_permission: bool,
) -> None:
    """Queued work revalidates both staff status and model permission."""
    actor = UserFactory(is_active=True, is_staff=is_staff, is_superuser=False)
    if grant_permission:
        actor.user_permissions.add(Permission.objects.get(codename="change_wirelesschassis"))
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


def test_queued_refresh_rejects_missing_actor_and_counts_only_valid_ids() -> None:
    """Malformed identifiers are discarded before a missing actor is denied."""
    result = ChassisRefreshService.refresh_authorized_ids(
        chassis_ids=[True, False, 0, -1, "12", 12],
        actor_id=999_999,
    )

    assert result.denied is True
    assert result.synced_count == 0
    assert result.failed_count == 1


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
