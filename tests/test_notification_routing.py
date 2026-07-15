"""Behavioral coverage for realtime notification routing."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from django.test import override_settings

import pytest

from micboard.services.notification.realtime_routing_service import (
    GLOBAL_UPDATES_GROUP,
    RealtimeRoutingService,
    campus_updates_group,
    organization_updates_group,
    site_updates_group,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1, 1), ("2", 2), (0, None), (-1, None), (None, None), ("bad", None)],
)
def test_identifier_normalization(value, expected) -> None:
    assert RealtimeRoutingService.normalize_identifier(value) == expected


def test_routing_scope_helpers_and_global_permission() -> None:
    user = SimpleNamespace(is_active=True, has_perm=Mock(return_value=True))
    assert RealtimeRoutingService.can_receive_global_updates(user)
    user.is_active = False
    assert not RealtimeRoutingService.can_receive_global_updates(user)
    assert RealtimeRoutingService.scope_from_mapping(
        {"organization_id": "2", "campus_id": "3"}
    ) == (
        2,
        3,
    )
    assert RealtimeRoutingService.scope_from_mapping({}) is None

    with override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=False):
        assert RealtimeRoutingService.groups_for_scope() == (GLOBAL_UPDATES_GROUP,)
    with override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=True, SITE_ID=7):
        assert RealtimeRoutingService.groups_for_scope() == (site_updates_group(7),)
        assert RealtimeRoutingService.groups_for_scope(site_id=9) == (site_updates_group(9),)
    with override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=True, SITE_ID=0):
        assert RealtimeRoutingService.groups_for_scope() == ()
    with override_settings(MICBOARD_MSP_ENABLED=True):
        assert RealtimeRoutingService.groups_for_scope() == ()
        assert RealtimeRoutingService.groups_for_scope(organization_id=2) == (
            organization_updates_group(2),
        )
        assert RealtimeRoutingService.groups_for_scope(organization_id=2, campus_id=3) == (
            organization_updates_group(2),
            campus_updates_group(2, 3),
        )


def _query_manager(rows=None, *, error: Exception | None = None):
    manager = Mock()
    if error is not None:
        manager.filter.side_effect = error
    else:
        queryset = manager.filter.return_value
        queryset.values_list.return_value = rows
    return manager


def test_routing_database_adapters_cover_rows_and_fail_closed(monkeypatch) -> None:
    chassis_manager = _query_manager([(1, 7), (2, None)])
    monkeypatch.setattr(
        "micboard.models.hardware.wireless_chassis.WirelessChassis",
        SimpleNamespace(_default_manager=chassis_manager),
    )
    assert RealtimeRoutingService.chassis_site_ids([1, 2]) == {1: 7}
    assert RealtimeRoutingService.hardware_site_id(device_type="WirelessChassis", device_id=1) == 7

    chassis_manager.filter.return_value.values_list.return_value = [
        (1, 10, 11),
        (2, None, None),
    ]
    assert RealtimeRoutingService.chassis_tenant_scopes([1, 2]) == {1: (10, 11)}
    assert RealtimeRoutingService.hardware_tenant_scope(
        device_type="WirelessChassis", device_id=1
    ) == (10, 11)
    assert RealtimeRoutingService.hardware_tenant_scope(device_type="Unknown", device_id=1) is None
    assert RealtimeRoutingService.hardware_site_id(device_type="Unknown", device_id=1) is None

    unit_manager = Mock()
    unit_query = unit_manager.filter.return_value.values_list.return_value
    unit_query.first.side_effect = [(20, 21), None, 8]
    monkeypatch.setattr(
        "micboard.models.hardware.wireless_unit.WirelessUnit",
        SimpleNamespace(_default_manager=unit_manager),
    )
    assert RealtimeRoutingService.hardware_tenant_scope(
        device_type="WirelessUnit", device_id=3
    ) == (20, 21)
    assert (
        RealtimeRoutingService.hardware_tenant_scope(device_type="WirelessUnit", device_id=4)
        is None
    )
    assert RealtimeRoutingService.hardware_site_id(device_type="WirelessUnit", device_id=3) == 8

    unit_manager.filter.side_effect = RuntimeError("query failed")
    assert (
        RealtimeRoutingService.hardware_tenant_scope(device_type="WirelessUnit", device_id=3)
        is None
    )
    assert RealtimeRoutingService.hardware_site_id(device_type="WirelessUnit", device_id=3) is None

    monkeypatch.setattr(
        "micboard.models.hardware.wireless_chassis.WirelessChassis",
        SimpleNamespace(_default_manager=_query_manager(error=RuntimeError("down"))),
    )
    assert RealtimeRoutingService.chassis_site_ids([1]) == {}
    assert RealtimeRoutingService.chassis_tenant_scopes([1]) == {}


def test_manufacturer_route_queries_cover_empty_success_and_failure(monkeypatch) -> None:
    assert RealtimeRoutingService.manufacturer_tenant_scopes(SimpleNamespace(pk=None)) == ()
    assert RealtimeRoutingService.manufacturer_site_ids(SimpleNamespace(pk=None)) == ()
    manager = Mock()
    queryset = manager.filter.return_value
    tenant_rows = Mock()
    tenant_rows.distinct.return_value = [(10, None), (20, 21), (None, None)]
    site_rows = Mock()
    site_rows.distinct.return_value = [7, 8]
    queryset.values_list.side_effect = [tenant_rows, site_rows]
    fake_chassis = SimpleNamespace(_default_manager=manager)
    monkeypatch.setattr(
        "micboard.models.hardware.wireless_chassis.WirelessChassis",
        fake_chassis,
    )
    manufacturer = SimpleNamespace(pk=3)
    assert RealtimeRoutingService.manufacturer_tenant_scopes(manufacturer) == (
        (10, None),
        (20, 21),
    )
    assert RealtimeRoutingService.manufacturer_site_ids(manufacturer) == (7, 8)

    manager.filter.side_effect = RuntimeError("query failed")
    assert RealtimeRoutingService.manufacturer_tenant_scopes(manufacturer) == ()
    assert RealtimeRoutingService.manufacturer_site_ids(manufacturer) == ()
