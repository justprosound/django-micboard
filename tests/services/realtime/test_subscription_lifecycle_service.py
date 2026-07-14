"""Tests for transport-neutral realtime subscription lifecycle behavior."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.realtime import subscription_lifecycle_service as lifecycle_service
from micboard.services.realtime.subscription_lifecycle_service import (
    RealtimeSubscriptionLifecycleService,
    RealtimeTransport,
)


def direct_sync_adapter(function, **_kwargs):
    """Adapt a sync callable without introducing a worker thread in unit tests."""

    async def invoke(*args, **kwargs):
        return function(*args, **kwargs)

    return invoke


def test_select_chassis_returns_explicit_bounded_chassis(monkeypatch) -> None:
    chassis = SimpleNamespace(pk=7)
    queryset = MagicMock()
    ordered_queryset = MagicMock()
    ordered_queryset.__getitem__.return_value = [chassis]
    queryset.filter.return_value.order_by.return_value = ordered_queryset
    initial_filter = Mock(return_value=queryset)
    fair_selector = Mock()
    monkeypatch.setattr(WirelessChassis.objects, "filter", initial_filter)
    monkeypatch.setattr(
        lifecycle_service.RealtimeSubscriptionSupervisor,
        "select_fair_queryset_batch",
        fair_selector,
    )

    selected = RealtimeSubscriptionLifecycleService.select_chassis(
        manufacturer_id=3,
        chassis_id=7,
        transport="sse",
        limit=2,
    )

    assert selected == [chassis]
    initial_filter.assert_called_once_with(
        manufacturer_id=3,
        manufacturer__is_active=True,
        status__in=("online", "degraded", "provisioning"),
    )
    queryset.filter.assert_called_once_with(pk=7)
    queryset.filter.return_value.order_by.assert_called_once_with("pk")
    ordered_queryset.__getitem__.assert_called_once_with(slice(None, 2))
    fair_selector.assert_not_called()


def test_select_chassis_delegates_unscoped_fairness(monkeypatch) -> None:
    chassis = SimpleNamespace(pk=8)
    queryset = MagicMock()
    monkeypatch.setattr(WirelessChassis.objects, "filter", Mock(return_value=queryset))
    fair_selector = Mock(return_value=[chassis])
    monkeypatch.setattr(
        lifecycle_service.RealtimeSubscriptionSupervisor,
        "select_fair_queryset_batch",
        fair_selector,
    )

    selected = RealtimeSubscriptionLifecycleService.select_chassis(
        manufacturer_id=4,
        chassis_id=None,
        transport="websocket",
        limit=5,
    )

    assert selected == [chassis]
    fair_selector.assert_called_once_with(
        queryset=queryset,
        transport="websocket",
        scope=4,
        limit=5,
    )


@pytest.mark.parametrize("transport", ["sse", "websocket"])
@pytest.mark.parametrize(
    ("transformed", "updated_count", "expect_update", "expect_broadcast"),
    [
        (None, 0, False, False),
        ({"name": "missing identifier"}, 0, False, False),
        ({"api_device_id": "one"}, 0, True, False),
        ({"api_device_id": "one"}, 1, True, True),
    ],
)
def test_process_update_branches(
    monkeypatch,
    transport: RealtimeTransport,
    transformed,
    updated_count,
    expect_update,
    expect_broadcast,
) -> None:
    manufacturer = SimpleNamespace(pk=9)
    plugin = SimpleNamespace(
        manufacturer=manufacturer,
        transform_device_data=Mock(return_value=transformed),
    )
    update = Mock(return_value=updated_count)
    broadcast = AsyncMock()
    monkeypatch.setattr(lifecycle_service, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(
        lifecycle_service.DeviceUpdateService,
        "update_models_from_api_data",
        update,
    )
    monkeypatch.setattr(
        RealtimeSubscriptionLifecycleService,
        "_broadcast_update_async",
        broadcast,
    )

    asyncio.run(
        RealtimeSubscriptionLifecycleService.process_update(
            plugin=plugin,
            data={"raw": True},
            transport=transport,
        )
    )

    assert update.call_count == int(expect_update)
    if expect_update:
        update.assert_called_once_with(
            api_data=[{"raw": True}],
            manufacturer=manufacturer,
            plugin=plugin,
        )
    assert broadcast.await_count == int(expect_broadcast)
    if expect_broadcast:
        broadcast.assert_awaited_once_with(
            manufacturer=manufacturer,
            api_device_id="one",
            transport=transport,
        )


@pytest.mark.parametrize("failure_stage", ["transform", "persist", "broadcast"])
def test_process_update_contains_and_redacts_failures(
    monkeypatch,
    caplog,
    failure_stage,
) -> None:
    secret = f"private-{failure_stage}-detail"
    manufacturer = SimpleNamespace(pk=10)
    plugin = SimpleNamespace(
        manufacturer=manufacturer,
        transform_device_data=Mock(return_value={"api_device_id": "one"}),
    )
    update = Mock(return_value=1)
    broadcast = AsyncMock()
    if failure_stage == "transform":
        plugin.transform_device_data.side_effect = RuntimeError(secret)
    elif failure_stage == "persist":
        update.side_effect = RuntimeError(secret)
    else:
        broadcast.side_effect = RuntimeError(secret)
    monkeypatch.setattr(lifecycle_service, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(
        lifecycle_service.DeviceUpdateService,
        "update_models_from_api_data",
        update,
    )
    monkeypatch.setattr(
        RealtimeSubscriptionLifecycleService,
        "_broadcast_update_async",
        broadcast,
    )
    caplog.set_level("DEBUG")

    asyncio.run(
        RealtimeSubscriptionLifecycleService.process_update(
            plugin=plugin,
            data={"raw": True},
            transport="sse",
        )
    )

    assert secret not in caplog.text
    assert "manufacturer ID 10" in caplog.text


@pytest.mark.parametrize(
    ("ip", "projected_ip"),
    [(None, None), ("192.0.2.1", "192.0.2.1")],
)
def test_project_chassis_uses_stable_primitive_payload(ip, projected_ip) -> None:
    chassis = SimpleNamespace(
        id=3,
        api_device_id="one",
        name="Receiver",
        ip=ip,
        status="online",
        model="EW-D",
    )

    projected = RealtimeSubscriptionLifecycleService._project_chassis(chassis)

    assert projected == {
        "id": 3,
        "api_device_id": "one",
        "name": "Receiver",
        "ip": projected_ip,
        "status": "online",
        "model": "EW-D",
    }


def test_broadcast_update_resolves_and_broadcasts_canonical_payload(monkeypatch) -> None:
    manufacturer = object()
    chassis = SimpleNamespace(
        id=3,
        api_device_id="one",
        name="Receiver",
        ip="192.0.2.1",
        status="online",
        model="ULXD",
    )
    get = Mock(return_value=chassis)
    broadcast = Mock()
    monkeypatch.setattr(WirelessChassis.objects, "get", get)
    monkeypatch.setattr(
        lifecycle_service.BroadcastService,
        "broadcast_device_update",
        broadcast,
    )

    RealtimeSubscriptionLifecycleService._broadcast_update(
        manufacturer=manufacturer,
        api_device_id="one",
    )

    get.assert_called_once_with(manufacturer=manufacturer, api_device_id="one")
    broadcast.assert_called_once_with(
        manufacturer=manufacturer,
        data={
            "receivers": [
                {
                    "id": 3,
                    "api_device_id": "one",
                    "name": "Receiver",
                    "ip": "192.0.2.1",
                    "status": "online",
                    "model": "ULXD",
                }
            ]
        },
    )


def test_broadcast_update_async_handles_success_missing_and_failure(
    monkeypatch,
    caplog,
) -> None:
    manufacturer = SimpleNamespace(pk=11)
    broadcast = Mock()
    monkeypatch.setattr(lifecycle_service, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(
        RealtimeSubscriptionLifecycleService,
        "_broadcast_update",
        broadcast,
    )
    caplog.set_level("DEBUG")

    asyncio.run(
        RealtimeSubscriptionLifecycleService._broadcast_update_async(
            manufacturer=manufacturer,
            api_device_id="one",
            transport="websocket",
        )
    )
    broadcast.assert_called_once_with(manufacturer=manufacturer, api_device_id="one")

    broadcast.side_effect = WirelessChassis.DoesNotExist
    asyncio.run(
        RealtimeSubscriptionLifecycleService._broadcast_update_async(
            manufacturer=manufacturer,
            api_device_id="missing",
            transport="sse",
        )
    )

    secret = "private-broadcast-failure"
    broadcast.side_effect = RuntimeError(secret)
    asyncio.run(
        RealtimeSubscriptionLifecycleService._broadcast_update_async(
            manufacturer=manufacturer,
            api_device_id="one",
            transport="sse",
        )
    )

    assert secret not in caplog.text
    assert "manufacturer ID 11" in caplog.text
