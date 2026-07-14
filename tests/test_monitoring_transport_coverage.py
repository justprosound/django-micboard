"""Behavioral coverage for SSE and WebSocket subscription services."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.realtime import (
    shure_websocket_subscription_service as websocket_tasks,
)
from micboard.services.realtime import sse_subscription_service as sse_tasks
from micboard.services.realtime.subscription_lifecycle_service import (
    RealtimeSubscriptionLifecycleService,
)


@pytest.fixture(autouse=True)
def isolated_supervisor_lease(monkeypatch):
    """Avoid sharing long-lived supervisor cache leases across service unit tests."""
    monkeypatch.setattr(
        sse_tasks.ManufacturerActivationService,
        "is_active",
        Mock(return_value=True),
    )
    monkeypatch.setattr(
        sse_tasks.RealtimeSubscriptionSupervisor,
        "acquire",
        Mock(return_value=Mock()),
    )
    selector = Mock(side_effect=lambda *, queryset, **_kwargs: list(queryset))
    monkeypatch.setattr(
        sse_tasks.RealtimeSubscriptionSupervisor,
        "select_fair_queryset_batch",
        selector,
    )
    return selector


def direct_sync_adapter(function, **_kwargs):
    """Adapt a sync callable without introducing a worker thread in unit tests."""

    async def invoke(*args, **kwargs):
        return function(*args, **kwargs)

    return invoke


def test_sse_service_handles_missing_capability_devices_and_errors(
    monkeypatch,
    isolated_supervisor_lease,
) -> None:
    manufacturer = SimpleNamespace(pk=1, code="vendor", name="Vendor")
    get = Mock(
        side_effect=[
            Manufacturer.DoesNotExist,
            manufacturer,
            manufacturer,
            manufacturer,
            RuntimeError("database unavailable"),
        ]
    )
    monkeypatch.setattr(sse_tasks.Manufacturer.objects, "get", get)
    unsupported = Mock(return_value=SimpleNamespace())
    supported = Mock(return_value=SimpleNamespace(connect_and_subscribe=AsyncMock()))
    plugin_loader = Mock(side_effect=[unsupported, supported, supported])
    monkeypatch.setattr(sse_tasks, "get_manufacturer_plugin", plugin_loader)
    isolated_supervisor_lease.side_effect = [
        [],
        [SimpleNamespace(api_device_id="one"), SimpleNamespace(api_device_id="two")],
    ]
    queryset = Mock()
    monkeypatch.setattr(sse_tasks.WirelessChassis.objects, "filter", Mock(return_value=queryset))
    run = Mock()
    monkeypatch.setattr(sse_tasks.asyncio, "run", run)

    sse_tasks.run_sse_subscriptions(99)
    sse_tasks.run_sse_subscriptions(1)
    sse_tasks.run_sse_subscriptions(1)
    sse_tasks.run_sse_subscriptions(1)
    sse_tasks.run_sse_subscriptions(1)

    run.assert_called_once()
    assert get.call_args_list[0].kwargs == {"pk": 99, "is_active": True}
    assert all(item.kwargs["is_active"] is True for item in get.call_args_list)
    coroutine = run.call_args.args[0]
    coroutine.close()


def test_sse_service_skips_external_work_when_supervisor_lease_is_held(monkeypatch) -> None:
    manufacturer = SimpleNamespace(pk=17, code="vendor", name="Vendor")
    plugin = SimpleNamespace(connect_and_subscribe=AsyncMock())
    queryset = SimpleNamespace(values_list=Mock(return_value=["device-1"]))
    monkeypatch.setattr(
        sse_tasks.Manufacturer.objects,
        "get",
        Mock(return_value=manufacturer),
    )
    monkeypatch.setattr(
        sse_tasks,
        "get_manufacturer_plugin",
        Mock(return_value=Mock(return_value=plugin)),
    )
    monkeypatch.setattr(
        sse_tasks.WirelessChassis.objects,
        "filter",
        Mock(return_value=queryset),
    )
    acquire = Mock(return_value=None)
    monkeypatch.setattr(sse_tasks.RealtimeSubscriptionSupervisor, "acquire", acquire)
    run = Mock()
    monkeypatch.setattr(sse_tasks.asyncio, "run", run)

    sse_tasks.run_sse_subscriptions(17)

    acquire.assert_called_once_with(transport="sse", scope=17)
    run.assert_not_called()


def test_sse_service_filters_one_persisted_chassis_id(monkeypatch) -> None:
    manufacturer = SimpleNamespace(pk=17, code="vendor")
    plugin = SimpleNamespace(connect_and_subscribe=AsyncMock())
    all_chassis = Mock()
    selected_chassis = MagicMock()
    all_chassis.filter.return_value = selected_chassis
    selected_chassis.order_by.return_value.__getitem__.return_value = [
        SimpleNamespace(api_device_id="device-1")
    ]
    monkeypatch.setattr(sse_tasks.Manufacturer.objects, "get", Mock(return_value=manufacturer))
    monkeypatch.setattr(
        sse_tasks,
        "get_manufacturer_plugin",
        Mock(return_value=Mock(return_value=plugin)),
    )
    monkeypatch.setattr(
        sse_tasks.WirelessChassis.objects,
        "filter",
        Mock(return_value=all_chassis),
    )
    run = Mock()
    monkeypatch.setattr(sse_tasks.asyncio, "run", run)

    sse_tasks.run_sse_subscriptions(17, chassis_id=27)

    all_chassis.filter.assert_called_once_with(pk=27)
    coroutine = run.call_args.args[0]
    coroutine.close()


def test_sse_service_reloads_next_fair_window_off_event_loop(
    monkeypatch,
    isolated_supervisor_lease,
) -> None:
    """The live supervisor receives a reload callback for later inventory windows."""
    manufacturer = SimpleNamespace(pk=17, code="vendor")
    plugin = SimpleNamespace(connect_and_subscribe=AsyncMock())
    first = SimpleNamespace(api_device_id="device-1")
    second = SimpleNamespace(api_device_id="device-2")
    isolated_supervisor_lease.side_effect = [[first], [second]]
    monkeypatch.setattr(sse_tasks.Manufacturer.objects, "get", Mock(return_value=manufacturer))
    monkeypatch.setattr(
        sse_tasks,
        "get_manufacturer_plugin",
        Mock(return_value=Mock(return_value=plugin)),
    )
    monkeypatch.setattr(sse_tasks.WirelessChassis.objects, "filter", Mock(return_value=Mock()))
    monkeypatch.setattr(sse_tasks, "sync_to_async", direct_sync_adapter)

    async def run_and_reload(*, items, reload_items, **_kwargs):
        assert items == ["device-1"]
        assert await reload_items() == ["device-2"]

    monkeypatch.setattr(sse_tasks.RealtimeSubscriptionSupervisor, "run", run_and_reload)

    sse_tasks.run_sse_subscriptions(17)

    assert isolated_supervisor_lease.call_count == 2


def test_sse_reload_stops_rotating_work_after_manufacturer_deactivation(
    monkeypatch,
    isolated_supervisor_lease,
) -> None:
    """A live SSE supervisor ends without selecting another stale inventory window."""
    manufacturer = SimpleNamespace(pk=17, code="vendor")
    first = SimpleNamespace(api_device_id="device-1")
    isolated_supervisor_lease.side_effect = [[first]]
    monkeypatch.setattr(sse_tasks.Manufacturer.objects, "get", Mock(return_value=manufacturer))
    monkeypatch.setattr(
        sse_tasks,
        "get_manufacturer_plugin",
        Mock(return_value=Mock(return_value=SimpleNamespace(connect_and_subscribe=AsyncMock()))),
    )
    monkeypatch.setattr(sse_tasks.WirelessChassis.objects, "filter", Mock(return_value=Mock()))
    monkeypatch.setattr(sse_tasks, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(
        sse_tasks.ManufacturerActivationService,
        "is_active",
        Mock(return_value=False),
    )

    async def run_and_reload(*, reload_items, **_kwargs):
        assert await reload_items() == []

    monkeypatch.setattr(sse_tasks.RealtimeSubscriptionSupervisor, "run", run_and_reload)

    sse_tasks.run_sse_subscriptions(17)

    assert isolated_supervisor_lease.call_count == 1


def test_websocket_service_skips_external_work_when_supervisor_lease_is_held(monkeypatch) -> None:
    from micboard.models.discovery.manufacturer import Manufacturer as ManufacturerModel
    from micboard.models.hardware.wireless_chassis import WirelessChassis as ChassisModel

    manufacturer = SimpleNamespace(pk=18, code="shure", name="Shure")
    monkeypatch.setattr(
        ManufacturerModel.objects,
        "get",
        Mock(return_value=manufacturer),
    )
    monkeypatch.setattr(
        websocket_tasks,
        "get_manufacturer_plugin",
        Mock(return_value=Mock(return_value=object())),
    )
    monkeypatch.setattr(
        ChassisModel.objects,
        "filter",
        Mock(return_value=[SimpleNamespace(api_device_id="device-1")]),
    )
    acquire = Mock(return_value=None)
    monkeypatch.setattr(websocket_tasks.RealtimeSubscriptionSupervisor, "acquire", acquire)
    run = Mock()
    monkeypatch.setattr(websocket_tasks.asyncio, "run", run)

    websocket_tasks.run_shure_websocket_subscriptions(18)

    acquire.assert_called_once_with(transport="websocket", scope=18)
    run.assert_not_called()


def test_websocket_service_filters_one_persisted_chassis_id(monkeypatch) -> None:
    manufacturer = SimpleNamespace(pk=18, code="shure")
    plugin = object()
    chassis = SimpleNamespace(pk=28, api_device_id="device-1")
    all_chassis = MagicMock()
    selected_chassis = MagicMock()
    all_chassis.filter.return_value = selected_chassis
    selected_chassis.order_by.return_value.__getitem__.return_value = [chassis]
    monkeypatch.setattr(
        websocket_tasks.Manufacturer.objects,
        "get",
        Mock(return_value=manufacturer),
    )
    monkeypatch.setattr(
        websocket_tasks,
        "get_manufacturer_plugin",
        Mock(return_value=Mock(return_value=plugin)),
    )
    monkeypatch.setattr(
        websocket_tasks.WirelessChassis.objects,
        "filter",
        Mock(return_value=all_chassis),
    )
    run = Mock()
    monkeypatch.setattr(websocket_tasks.asyncio, "run", run)

    websocket_tasks.run_shure_websocket_subscriptions(18, chassis_id=28)

    all_chassis.filter.assert_called_once_with(pk=28)
    coroutine = run.call_args.args[0]
    coroutine.close()


def test_websocket_service_reloads_next_fair_window_off_event_loop(
    monkeypatch,
    isolated_supervisor_lease,
) -> None:
    """Shure supervision reloads the next bounded chassis window under the same lease."""
    manufacturer = SimpleNamespace(pk=18, code="shure")
    first = SimpleNamespace(pk=1, api_device_id="device-1")
    second = SimpleNamespace(pk=2, api_device_id="device-2")
    isolated_supervisor_lease.side_effect = [[first], [second]]
    monkeypatch.setattr(
        websocket_tasks.Manufacturer.objects,
        "get",
        Mock(return_value=manufacturer),
    )
    monkeypatch.setattr(
        websocket_tasks,
        "get_manufacturer_plugin",
        Mock(return_value=Mock(return_value=object())),
    )
    monkeypatch.setattr(
        websocket_tasks.WirelessChassis.objects,
        "filter",
        Mock(return_value=Mock()),
    )
    monkeypatch.setattr(websocket_tasks, "sync_to_async", direct_sync_adapter)

    async def run_and_reload(*, items, reload_items, **_kwargs):
        assert items == [first]
        assert await reload_items() == [second]

    monkeypatch.setattr(
        websocket_tasks.RealtimeSubscriptionSupervisor,
        "run",
        run_and_reload,
    )

    websocket_tasks.run_shure_websocket_subscriptions(18)

    assert isolated_supervisor_lease.call_count == 2


def test_websocket_reload_stops_after_manufacturer_deactivation(
    monkeypatch,
    isolated_supervisor_lease,
) -> None:
    """A live WebSocket supervisor ends without selecting more stale chassis."""
    manufacturer = SimpleNamespace(pk=18, code="shure")
    first = SimpleNamespace(pk=1, api_device_id="device-1")
    isolated_supervisor_lease.side_effect = [[first]]
    monkeypatch.setattr(
        websocket_tasks.Manufacturer.objects,
        "get",
        Mock(return_value=manufacturer),
    )
    monkeypatch.setattr(
        websocket_tasks,
        "get_manufacturer_plugin",
        Mock(return_value=Mock(return_value=object())),
    )
    monkeypatch.setattr(
        websocket_tasks.WirelessChassis.objects,
        "filter",
        Mock(return_value=Mock()),
    )
    monkeypatch.setattr(websocket_tasks, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(
        websocket_tasks.ManufacturerActivationService,
        "is_active",
        Mock(return_value=False),
    )

    async def run_and_reload(*, reload_items, **_kwargs):
        assert await reload_items() == []

    monkeypatch.setattr(
        websocket_tasks.RealtimeSubscriptionSupervisor,
        "run",
        run_and_reload,
    )

    websocket_tasks.run_shure_websocket_subscriptions(18)

    assert isolated_supervisor_lease.call_count == 1


def test_get_or_create_sse_connection_updates_existing_tracking(monkeypatch) -> None:
    from micboard.models.realtime.connection import RealTimeConnection

    manufacturer = object()
    plugin = SimpleNamespace(manufacturer=manufacturer)
    chassis = object()
    connection = SimpleNamespace(connection_type="websocket", save=Mock())
    monkeypatch.setattr(sse_tasks.WirelessChassis.objects, "get", Mock(return_value=chassis))
    monkeypatch.setattr(
        RealTimeConnection.objects,
        "get_or_create",
        Mock(return_value=(connection, False)),
    )
    mark = Mock()
    monkeypatch.setattr(sse_tasks, "mark_connecting", mark)

    assert sse_tasks._get_or_create_sse_connection(plugin, "one") is connection
    assert connection.connection_type == "sse"
    connection.save.assert_called_once_with(update_fields=["connection_type", "updated_at"])
    mark.assert_called_once_with(connection)

    RealTimeConnection.objects.get_or_create.return_value = (connection, True)
    connection.save.reset_mock()
    sse_tasks._get_or_create_sse_connection(plugin, "one")
    connection.save.assert_not_called()


def test_subscribe_sse_redacts_payloads_and_connectionless_failures(monkeypatch, caplog) -> None:
    plugin = SimpleNamespace(
        manufacturer=SimpleNamespace(pk=17),
        connect_and_subscribe=AsyncMock(),
    )
    secret = "private-event-payload"
    caplog.set_level("DEBUG")

    async def deliver(_device, callback):
        await callback({"id": "one", "secret": secret})

    plugin.connect_and_subscribe.side_effect = deliver
    process = AsyncMock()
    monkeypatch.setattr(
        sse_tasks.RealtimeSubscriptionLifecycleService,
        "process_update",
        process,
    )
    monkeypatch.setattr(sse_tasks, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(
        sse_tasks,
        "_get_or_create_sse_connection",
        Mock(side_effect=WirelessChassis.DoesNotExist),
    )

    asyncio.run(sse_tasks._subscribe_device_async(plugin, "one"))

    process.assert_awaited_once_with(
        plugin=plugin,
        data={"id": "one", "secret": secret},
        transport="sse",
    )
    assert secret not in caplog.text

    failure_secret = "private-stream-credential"
    plugin.connect_and_subscribe = AsyncMock(side_effect=RuntimeError(failure_secret))
    asyncio.run(sse_tasks._subscribe_device_async(plugin, "one"))
    assert failure_secret not in caplog.text


def test_subscribe_sse_stops_before_outbound_when_manufacturer_deactivates(
    monkeypatch,
) -> None:
    """A live SSE round rechecks current activation after tracking setup."""
    connection = object()
    plugin = SimpleNamespace(
        manufacturer=SimpleNamespace(pk=17),
        connect_and_subscribe=AsyncMock(),
    )
    monkeypatch.setattr(sse_tasks, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(
        sse_tasks,
        "_get_or_create_sse_connection",
        Mock(return_value=connection),
    )
    monkeypatch.setattr(
        sse_tasks.ManufacturerActivationService,
        "is_active",
        Mock(return_value=False),
    )
    stopped = Mock()
    monkeypatch.setattr(sse_tasks, "mark_stopped", stopped)

    asyncio.run(sse_tasks._subscribe_device_async(plugin, "one"))

    plugin.connect_and_subscribe.assert_not_awaited()
    stopped.assert_called_once_with(connection)


def test_subscribe_sse_rejects_missing_manufacturer_identity(monkeypatch) -> None:
    plugin = SimpleNamespace(
        manufacturer=SimpleNamespace(pk=None),
        connect_and_subscribe=AsyncMock(),
    )
    create_connection = Mock()
    monkeypatch.setattr(sse_tasks, "_get_or_create_sse_connection", create_connection)

    asyncio.run(sse_tasks._subscribe_device_async(plugin, "one"))

    create_connection.assert_not_called()
    plugin.connect_and_subscribe.assert_not_awaited()


def test_subscribe_sse_stops_connectionless_inactive_round(monkeypatch) -> None:
    plugin = SimpleNamespace(
        manufacturer=SimpleNamespace(pk=17),
        connect_and_subscribe=AsyncMock(),
    )
    monkeypatch.setattr(sse_tasks, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(
        sse_tasks,
        "_get_or_create_sse_connection",
        Mock(side_effect=WirelessChassis.DoesNotExist),
    )
    monkeypatch.setattr(
        sse_tasks.ManufacturerActivationService,
        "is_active",
        Mock(return_value=False),
    )

    asyncio.run(sse_tasks._subscribe_device_async(plugin, "one"))

    plugin.connect_and_subscribe.assert_not_awaited()


def test_start_websocket_subscriptions_handles_missing_and_empty_manufacturer(monkeypatch) -> None:
    from micboard.models.discovery.manufacturer import Manufacturer as ManufacturerModel
    from micboard.models.hardware.wireless_chassis import WirelessChassis as ChassisModel

    get = Mock(
        side_effect=[
            ManufacturerModel.DoesNotExist,
            SimpleNamespace(pk=21, code="shure"),
        ]
    )
    monkeypatch.setattr(ManufacturerModel.objects, "get", get)
    monkeypatch.setattr(ChassisModel.objects, "filter", Mock(return_value=[]))

    websocket_tasks.run_shure_websocket_subscriptions(20)
    websocket_tasks.run_shure_websocket_subscriptions(21)

    assert get.call_args_list[0].kwargs == {
        "pk": 20,
        "code": "shure",
        "is_active": True,
    }


def test_start_websocket_subscriptions_runs_each_chassis_and_contains_outer_error(
    monkeypatch,
) -> None:
    from micboard.models.discovery.manufacturer import Manufacturer as ManufacturerModel
    from micboard.models.hardware.wireless_chassis import WirelessChassis as ChassisModel

    manufacturer = SimpleNamespace(pk=22, code="shure")
    chassis = [SimpleNamespace(name="One"), SimpleNamespace(name="Two")]
    monkeypatch.setattr(
        ManufacturerModel.objects,
        "get",
        Mock(side_effect=[manufacturer, RuntimeError("database unavailable")]),
    )
    monkeypatch.setattr(ChassisModel.objects, "filter", Mock(return_value=chassis))
    plugin = object()
    monkeypatch.setattr(
        websocket_tasks, "get_manufacturer_plugin", Mock(return_value=Mock(return_value=plugin))
    )
    start = AsyncMock()
    monkeypatch.setattr(websocket_tasks, "_start_receiver_websocket_async", start)

    async def run_one_round(*, items, subscribe, **_kwargs):
        for item in items:
            await subscribe(item)

    monkeypatch.setattr(
        websocket_tasks.RealtimeSubscriptionSupervisor,
        "run",
        run_one_round,
    )

    websocket_tasks.run_shure_websocket_subscriptions(22)
    websocket_tasks.run_shure_websocket_subscriptions(22)

    assert [item.args[1].name for item in start.await_args_list] == ["One", "Two"]


def test_start_websocket_subscriptions_handles_empty_iteration_after_existence_check(
    monkeypatch,
) -> None:
    from micboard.models.discovery.manufacturer import Manufacturer as ManufacturerModel
    from micboard.models.hardware.wireless_chassis import WirelessChassis as ChassisModel

    class ChangedQueryset:
        def __bool__(self):
            return True

        def __iter__(self):
            return iter(())

        def __getitem__(self, _index):
            return self

    manufacturer = SimpleNamespace(pk=23, code="shure")
    monkeypatch.setattr(ManufacturerModel.objects, "get", Mock(return_value=manufacturer))
    monkeypatch.setattr(ChassisModel.objects, "filter", Mock(return_value=ChangedQueryset()))
    monkeypatch.setattr(
        websocket_tasks,
        "get_manufacturer_plugin",
        Mock(return_value=Mock(return_value=object())),
    )
    websocket_tasks.run_shure_websocket_subscriptions(23)


def test_get_or_create_websocket_connection_updates_existing_tracking(monkeypatch) -> None:
    from micboard.models.realtime.connection import RealTimeConnection

    chassis = object()
    connection = SimpleNamespace(connection_type="sse", save=Mock())
    monkeypatch.setattr(
        RealTimeConnection.objects,
        "get_or_create",
        Mock(return_value=(connection, False)),
    )
    mark = Mock()
    monkeypatch.setattr(websocket_tasks, "mark_connecting", mark)
    assert websocket_tasks._get_or_create_websocket_connection(chassis) is connection
    assert connection.connection_type == "websocket"
    connection.save.assert_called_once_with(update_fields=["connection_type", "updated_at"])
    mark.assert_called_once_with(connection)

    RealTimeConnection.objects.get_or_create.return_value = (connection, True)
    connection.save.reset_mock()
    websocket_tasks._get_or_create_websocket_connection(chassis)
    connection.save.assert_not_called()


def test_websocket_subscription_redacts_preconnection_and_close_errors(monkeypatch, caplog) -> None:
    plugin = SimpleNamespace(manufacturer=SimpleNamespace(pk=18))
    chassis = SimpleNamespace(name="Receiver", ip="192.0.2.1", port=2420, api_device_id="one")
    tracking_secret = "private-tracking-detail"
    close_secret = "private-close-detail"
    monkeypatch.setattr(websocket_tasks, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(
        websocket_tasks,
        "_get_or_create_websocket_connection",
        Mock(side_effect=RuntimeError(tracking_secret)),
    )
    asyncio.run(websocket_tasks._start_receiver_websocket_async(plugin, chassis))

    connection = object()
    client = SimpleNamespace(close=Mock(side_effect=RuntimeError(close_secret)))
    monkeypatch.setattr(
        websocket_tasks, "_get_or_create_websocket_connection", Mock(return_value=connection)
    )
    monkeypatch.setattr(
        "micboard.integrations.shure.client.ShureSystemAPIClient",
        Mock(return_value=client),
    )
    monkeypatch.setattr(websocket_tasks, "connect_and_subscribe", AsyncMock())
    asyncio.run(websocket_tasks._start_receiver_websocket_async(plugin, chassis))
    client.close.assert_called_once_with()
    assert tracking_secret not in caplog.text
    assert close_secret not in caplog.text


def test_websocket_callback_delegates_to_shared_lifecycle(monkeypatch) -> None:
    plugin = SimpleNamespace(manufacturer=SimpleNamespace(pk=18))
    chassis = SimpleNamespace(
        pk=28,
        ip="192.0.2.28",
        port=443,
        api_device_id="one",
    )
    client = SimpleNamespace(close=Mock())
    process = AsyncMock()

    async def deliver(_client, _device_id, callback):
        await callback({"id": "one"})

    monkeypatch.setattr(websocket_tasks, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(
        websocket_tasks,
        "_get_or_create_websocket_connection",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(websocket_tasks, "received_message", Mock())
    monkeypatch.setattr(
        "micboard.integrations.shure.client.ShureSystemAPIClient",
        Mock(return_value=client),
    )
    monkeypatch.setattr(websocket_tasks, "connect_and_subscribe", AsyncMock(side_effect=deliver))
    monkeypatch.setattr(
        websocket_tasks.RealtimeSubscriptionLifecycleService,
        "process_update",
        process,
    )

    asyncio.run(websocket_tasks._start_receiver_websocket_async(plugin, chassis))

    process.assert_awaited_once_with(
        plugin=plugin,
        data={"id": "one"},
        transport="websocket",
    )
    client.close.assert_called_once_with()


def test_websocket_subscription_uses_bracketed_ipv6_origin(monkeypatch) -> None:
    """The WebSocket client receives a valid HTTPS authority for IPv6 chassis."""
    plugin = SimpleNamespace(manufacturer=SimpleNamespace(pk=18))
    chassis = SimpleNamespace(
        name="IPv6 Receiver",
        ip="2001:db8::25",
        port=8443,
        api_device_id="one",
    )
    client = SimpleNamespace(close=Mock())
    client_class = Mock(return_value=client)
    monkeypatch.setattr(websocket_tasks, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(
        websocket_tasks,
        "_get_or_create_websocket_connection",
        Mock(return_value=object()),
    )
    monkeypatch.setattr(
        "micboard.integrations.shure.client.ShureSystemAPIClient",
        client_class,
    )
    monkeypatch.setattr(websocket_tasks, "connect_and_subscribe", AsyncMock())

    asyncio.run(websocket_tasks._start_receiver_websocket_async(plugin, chassis))

    client_class.assert_called_once_with(base_url="https://[2001:db8::25]:8443")


def test_websocket_subscription_stops_before_outbound_when_manufacturer_deactivates(
    monkeypatch,
) -> None:
    """A live WebSocket round rechecks current activation before connecting."""
    plugin = SimpleNamespace(manufacturer=SimpleNamespace(pk=18))
    chassis = SimpleNamespace(
        pk=28,
        ip="192.0.2.28",
        port=443,
        api_device_id="one",
    )
    connection = object()
    client = SimpleNamespace(close=Mock())
    monkeypatch.setattr(websocket_tasks, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(
        websocket_tasks,
        "_get_or_create_websocket_connection",
        Mock(return_value=connection),
    )
    monkeypatch.setattr(
        "micboard.integrations.shure.client.ShureSystemAPIClient",
        Mock(return_value=client),
    )
    monkeypatch.setattr(
        websocket_tasks.ManufacturerActivationService,
        "is_active",
        Mock(return_value=False),
    )
    stopped = Mock()
    connect = AsyncMock()
    monkeypatch.setattr(websocket_tasks, "mark_stopped", stopped)
    monkeypatch.setattr(websocket_tasks, "connect_and_subscribe", connect)

    asyncio.run(websocket_tasks._start_receiver_websocket_async(plugin, chassis))

    connect.assert_not_awaited()
    stopped.assert_called_once_with(connection)
    client.close.assert_called_once_with()


def test_websocket_subscription_rejects_missing_manufacturer_identity(monkeypatch) -> None:
    plugin = SimpleNamespace(manufacturer=SimpleNamespace(pk=None))
    chassis = SimpleNamespace(
        pk=28,
        ip="192.0.2.28",
        port=443,
        api_device_id="one",
    )
    connection = object()
    client = SimpleNamespace(close=Mock())
    stopped = Mock()
    connect = AsyncMock()
    monkeypatch.setattr(websocket_tasks, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(
        websocket_tasks,
        "_get_or_create_websocket_connection",
        Mock(return_value=connection),
    )
    monkeypatch.setattr(
        "micboard.integrations.shure.client.ShureSystemAPIClient",
        Mock(return_value=client),
    )
    monkeypatch.setattr(websocket_tasks, "mark_stopped", stopped)
    monkeypatch.setattr(websocket_tasks, "connect_and_subscribe", connect)

    asyncio.run(websocket_tasks._start_receiver_websocket_async(plugin, chassis))

    stopped.assert_called_once_with(connection)
    connect.assert_not_awaited()
    client.close.assert_called_once_with()


def test_realtime_transport_logs_exclude_vendor_and_device_sentinels(
    monkeypatch,
    caplog,
) -> None:
    """Realtime logs retain numeric model context without vendor-controlled identifiers."""
    manufacturer_code = "secret-vendor-code"
    manufacturer_name = "secret vendor display name"
    device_id = "secret-device-identifier"
    chassis_name = "secret chassis display name"
    transport_secret = "secret transport credential"
    manufacturer = SimpleNamespace(
        pk=41,
        code=manufacturer_code,
        name=manufacturer_name,
    )
    caplog.set_level("DEBUG")

    sse_plugin = SimpleNamespace(
        manufacturer=manufacturer,
        connect_and_subscribe=AsyncMock(side_effect=RuntimeError(transport_secret)),
        transform_device_data=Mock(return_value=None),
    )
    monkeypatch.setattr(sse_tasks, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(
        sse_tasks,
        "_get_or_create_sse_connection",
        Mock(side_effect=WirelessChassis.DoesNotExist),
    )
    asyncio.run(sse_tasks._subscribe_device_async(sse_plugin, device_id))
    asyncio.run(
        RealtimeSubscriptionLifecycleService.process_update(
            plugin=sse_plugin,
            data={},
            transport="sse",
        )
    )

    websocket_plugin = SimpleNamespace(
        manufacturer=manufacturer,
        transform_device_data=Mock(return_value=None),
    )
    chassis = SimpleNamespace(
        pk=42,
        name=chassis_name,
        api_device_id=device_id,
        ip="192.0.2.42",
        port=443,
    )
    monkeypatch.setattr(websocket_tasks, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(
        websocket_tasks,
        "_get_or_create_websocket_connection",
        Mock(side_effect=RuntimeError(transport_secret)),
    )
    asyncio.run(websocket_tasks._start_receiver_websocket_async(websocket_plugin, chassis))
    asyncio.run(
        RealtimeSubscriptionLifecycleService.process_update(
            plugin=websocket_plugin,
            data={},
            transport="websocket",
        )
    )

    for sentinel in (
        manufacturer_code,
        manufacturer_name,
        device_id,
        chassis_name,
        transport_secret,
    ):
        assert sentinel not in caplog.text
    assert "manufacturer ID 41" in caplog.text
    assert "chassis ID 42" in caplog.text
