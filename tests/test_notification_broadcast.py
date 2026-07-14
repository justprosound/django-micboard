"""Behavioral coverage for scoped realtime notification broadcasts."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, call

from django.test import override_settings

import pytest

from micboard.services.notification import broadcast_service as broadcast_module
from micboard.services.notification.broadcast_service import BroadcastService
from micboard.services.notification.realtime_routing_service import RealtimeRoutingService


def test_broadcast_sender_deduplicates_and_contains_group_failures(monkeypatch) -> None:
    send = Mock(side_effect=[None, RuntimeError("group unavailable")])
    layer = SimpleNamespace(group_send=Mock())
    monkeypatch.setattr(broadcast_module, "get_channel_layer", Mock(return_value=layer))
    monkeypatch.setattr(broadcast_module, "async_to_sync", Mock(return_value=send))
    BroadcastService._send_to_groups({"type": "event"}, ["one", "one", "two"])
    assert send.call_args_list == [call("one", {"type": "event"}), call("two", {"type": "event"})]

    BroadcastService._send_to_groups({"type": "event"}, [])
    monkeypatch.setattr(broadcast_module, "get_channel_layer", Mock(return_value=None))
    BroadcastService._send_to_groups({"type": "event"}, ["one"])
    monkeypatch.setattr(
        broadcast_module, "get_channel_layer", Mock(side_effect=RuntimeError("down"))
    )
    BroadcastService._send_to_groups({"type": "event"}, ["one"])


def test_broadcast_group_expansion_and_partition_edge_cases(monkeypatch) -> None:
    send = Mock()
    groups = Mock(side_effect=[("site.1",), ("site.2",), ("org.1",), ("org.2",)])
    monkeypatch.setattr(BroadcastService, "_send_to_groups", send)
    monkeypatch.setattr(RealtimeRoutingService, "groups_for_scope", groups)
    BroadcastService._send_for_sites({"type": "health"}, [1, 2])
    assert send.call_args.args[1] == ["site.1", "site.2"]
    BroadcastService._send_for_scopes({"type": "health"}, [(1, None), (2, 3)])
    assert send.call_args.args[1] == ["org.1", "org.2"]

    manufacturer = SimpleNamespace(code="vendor")
    send_scope = Mock()
    monkeypatch.setattr(BroadcastService, "_send_for_scope", send_scope)
    monkeypatch.setattr(
        RealtimeRoutingService,
        "chassis_tenant_scopes",
        Mock(return_value={2: (20, None)}),
    )
    BroadcastService._broadcast_partitioned_device_data(
        manufacturer=manufacturer,
        data={
            "receivers": [
                "invalid",
                {"id": 1, "organization_id": 10, "campus_id": 11},
                {"id": 2},
            ]
        },
    )
    assert send_scope.call_count == 2

    send_scope.reset_mock()
    monkeypatch.setattr(RealtimeRoutingService, "chassis_site_ids", Mock(return_value={2: 8}))
    BroadcastService._broadcast_partitioned_site_data(
        manufacturer=manufacturer,
        data={
            "receivers": [
                "invalid",
                {"id": 1, "site_id": 7},
                {"id": 2},
                {"id": "bad"},
            ]
        },
    )
    assert [item.kwargs["site_id"] for item in send_scope.call_args_list] == [7, 8]
    BroadcastService._broadcast_partitioned_site_data(manufacturer=manufacturer, data={})
    BroadcastService._broadcast_partitioned_site_data(
        manufacturer=manufacturer,
        data={"receivers": ["invalid", {"id": "bad"}]},
    )


@override_settings(MICBOARD_MSP_ENABLED=True, MICBOARD_MULTI_SITE_MODE=False)
def test_msp_broadcast_explicit_and_embedded_scopes(monkeypatch) -> None:
    send = Mock()
    monkeypatch.setattr(BroadcastService, "_send_to_groups", send)
    manufacturer = SimpleNamespace(code="vendor")
    BroadcastService.broadcast_device_update(
        manufacturer=manufacturer,
        data={"value": 1},
        organization_id=10,
        campus_id=11,
    )
    BroadcastService.broadcast_device_update(
        manufacturer=manufacturer,
        data={"organization_id": 20, "campus_id": 21},
    )
    monkeypatch.setattr(
        RealtimeRoutingService,
        "chassis_tenant_scopes",
        Mock(return_value={3: (30, None)}),
    )
    BroadcastService.broadcast_device_update(
        manufacturer=manufacturer,
        data={"value": 2},
        chassis_id=3,
    )
    assert send.call_count == 3

    BroadcastService._broadcast_partitioned_device_data(manufacturer=manufacturer, data={})
    BroadcastService._broadcast_partitioned_device_data(
        manufacturer=manufacturer,
        data={"receivers": ["invalid", {"id": "bad"}]},
    )
    BroadcastService.broadcast_device_update(manufacturer=manufacturer, data="unscoped")


@override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=True, SITE_ID=1)
def test_multisite_broadcast_resolution_and_fail_closed_paths(monkeypatch) -> None:
    send_scope = Mock()
    partition = Mock()
    monkeypatch.setattr(BroadcastService, "_send_for_scope", send_scope)
    monkeypatch.setattr(BroadcastService, "_broadcast_partitioned_site_data", partition)
    monkeypatch.setattr(
        RealtimeRoutingService,
        "chassis_site_ids",
        Mock(side_effect=[{3: 7}, {}]),
    )
    manufacturer = SimpleNamespace(code="vendor")

    BroadcastService.broadcast_device_update(
        manufacturer=manufacturer, data={"value": 1}, chassis_id=3
    )
    BroadcastService.broadcast_device_update(manufacturer=manufacturer, data={"site_id": 8})
    BroadcastService.broadcast_device_update(manufacturer=manufacturer, data={"receivers": []})
    BroadcastService.broadcast_device_update(manufacturer=manufacturer, data="unscoped")
    assert send_scope.call_count == 2
    partition.assert_called_once()

    BroadcastService._broadcast_partitioned_site_data(manufacturer=manufacturer, data={})
    monkeypatch.setattr(RealtimeRoutingService, "chassis_site_ids", Mock(return_value={}))
    BroadcastService._broadcast_partitioned_site_data(
        manufacturer=manufacturer,
        data={"receivers": ["invalid", {"id": "bad"}]},
    )


def test_single_site_device_update_and_unresolved_multisite_status(monkeypatch) -> None:
    send_scope = Mock()
    monkeypatch.setattr(BroadcastService, "_send_for_scope", send_scope)
    manufacturer = SimpleNamespace(code="vendor")
    with override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=False):
        BroadcastService.broadcast_device_update(manufacturer=manufacturer, data={"id": 1})
    assert send_scope.called

    send_scope.reset_mock()
    with override_settings(MICBOARD_MSP_ENABLED=False, MICBOARD_MULTI_SITE_MODE=True):
        monkeypatch.setattr(RealtimeRoutingService, "hardware_site_id", Mock(return_value=None))
        BroadcastService.broadcast_device_status(
            service_code="vendor",
            device_id=3,
            device_type="WirelessChassis",
            status="offline",
            is_active=False,
        )
    send_scope.assert_not_called()


@pytest.mark.parametrize(
    "settings_values",
    [
        {"MICBOARD_MSP_ENABLED": False, "MICBOARD_MULTI_SITE_MODE": False},
        {"MICBOARD_MSP_ENABLED": False, "MICBOARD_MULTI_SITE_MODE": True},
        {"MICBOARD_MSP_ENABLED": True, "MICBOARD_MULTI_SITE_MODE": False},
    ],
)
def test_live_broadcast_families_construct_scoped_payloads(monkeypatch, settings_values) -> None:
    send_scope = Mock()
    send_scopes = Mock()
    send_sites = Mock()
    monkeypatch.setattr(BroadcastService, "_send_for_scope", send_scope)
    monkeypatch.setattr(BroadcastService, "_send_for_scopes", send_scopes)
    monkeypatch.setattr(BroadcastService, "_send_for_sites", send_sites)
    monkeypatch.setattr(
        RealtimeRoutingService, "manufacturer_tenant_scopes", Mock(return_value=((1, 2),))
    )
    monkeypatch.setattr(RealtimeRoutingService, "manufacturer_site_ids", Mock(return_value=(7,)))
    manufacturer = SimpleNamespace(pk=3, code="vendor")

    with override_settings(**settings_values):
        BroadcastService.broadcast_api_health(
            manufacturer=manufacturer, health_data={"status": "healthy"}
        )
        BroadcastService.broadcast_device_status(
            service_code="vendor",
            device_id=3,
            device_type="WirelessChassis",
            status="online",
            is_active=True,
            organization_id=1,
            campus_id=2,
            site_id=7,
        )
    assert send_scope.called or send_scopes.called or send_sites.called
