"""Selected chassis refresh service regressions."""

from __future__ import annotations

from typing import Any

from django.db import connection
from django.utils import timezone

import pytest

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.hardware.chassis_refresh_service import ChassisRefreshService
from tests.factories.hardware import WirelessChassisFactory

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
    monkeypatch.setattr(type(chassis.manufacturer), "get_plugin_class", lambda _self: _Plugin)

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
    monkeypatch.setattr(type(chassis.manufacturer), "get_plugin_class", lambda _self: _Plugin)
    _Plugin.observed_atomic_blocks = []

    ChassisRefreshService.refresh_ids(chassis_ids=[chassis.pk])

    assert _Plugin.observed_atomic_blocks == [False]


def test_refresh_never_widens_selected_queryset(monkeypatch: pytest.MonkeyPatch) -> None:
    """A shared manufacturer must not turn one selected row into a global poll."""
    selected = WirelessChassisFactory(status="online")
    unselected = WirelessChassisFactory(manufacturer=selected.manufacturer, status="online")
    monkeypatch.setattr(type(selected.manufacturer), "get_plugin_class", lambda _self: _Plugin)
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
    monkeypatch.setattr(type(chassis.manufacturer), "get_plugin_class", lambda _self: _Plugin)

    result = ChassisRefreshService.refresh(queryset=WirelessChassis.objects.filter(pk=chassis.pk))

    chassis.refresh_from_db()
    assert result.synced_count == 0
    assert result.failed_count == 1
    assert chassis.name == original_name
    assert chassis.status == "offline"
