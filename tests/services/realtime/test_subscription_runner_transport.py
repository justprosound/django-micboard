"""Transport-neutral behaviour of one realtime subscription round.

These cover the runner's orchestration — leasing, inventory windows, activation rechecks,
connection tracking, and redaction — with the vendor stream and the database mocked out.
Both transports run through the same code, so each behaviour is asserted once.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from micboard.services.realtime import subscription_runner as runner
from micboard.services.realtime.subscription_lifecycle_service import (
    RealtimeSubscriptionLifecycleService,
)


@pytest.fixture(autouse=True)
def isolated_supervisor_lease(monkeypatch):
    """Avoid sharing long-lived supervisor cache leases across service unit tests."""
    monkeypatch.setattr(
        runner.ManufacturerActivationService,
        "is_active",
        Mock(return_value=True),
    )
    monkeypatch.setattr(
        runner.RealtimeSubscriptionSupervisor,
        "acquire",
        Mock(return_value=Mock()),
    )
    selector = Mock(side_effect=lambda *, queryset, **_kwargs: list(queryset))
    monkeypatch.setattr(
        runner.RealtimeSubscriptionSupervisor,
        "select_fair_queryset_batch",
        selector,
    )
    return selector


def direct_sync_adapter(function, **_kwargs):
    """Adapt a sync callable without introducing a worker thread in unit tests."""

    async def invoke(*args, **kwargs):
        return function(*args, **kwargs)

    return invoke


def _plugin(transport: str = "sse", **overrides):
    """Build a plugin double bound to a manufacturer with the given transport."""
    attributes = {
        "manufacturer": SimpleNamespace(pk=17, code="vendor", name="Vendor"),
        "realtime_transport": transport,
        "subscribe_to_chassis": AsyncMock(),
    }
    attributes.update(overrides)
    return SimpleNamespace(**attributes)


def _bind(monkeypatch, plugin) -> None:
    monkeypatch.setattr(runner, "build_manufacturer_plugin", Mock(return_value=plugin))


def test_a_missing_or_inactive_manufacturer_does_no_outbound_work(monkeypatch) -> None:
    """A stale queued manufacturer ID stops before a plugin is ever built."""
    monkeypatch.setattr(
        runner.Manufacturer.objects,
        "get",
        Mock(side_effect=runner.Manufacturer.DoesNotExist),
    )
    build = Mock()
    monkeypatch.setattr(runner, "build_manufacturer_plugin", build)

    runner.run_realtime_subscriptions(99)

    build.assert_not_called()


def test_a_held_lease_skips_external_work(monkeypatch) -> None:
    """Only one supervisor per transport and manufacturer may open connections."""
    plugin = _plugin()
    monkeypatch.setattr(
        runner.Manufacturer.objects,
        "get",
        Mock(return_value=plugin.manufacturer),
    )
    _bind(monkeypatch, plugin)
    monkeypatch.setattr(
        runner.WirelessChassis.objects,
        "filter",
        Mock(return_value=SimpleNamespace(values_list=Mock(return_value=["device-1"]))),
    )
    acquire = Mock(return_value=None)
    monkeypatch.setattr(runner.RealtimeSubscriptionSupervisor, "acquire", acquire)
    run = Mock()
    monkeypatch.setattr(runner.asyncio, "run", run)

    runner.run_realtime_subscriptions(17)

    acquire.assert_called_once_with(transport="sse", scope=17)
    run.assert_not_called()


def test_an_empty_inventory_starts_no_supervisor(monkeypatch) -> None:
    """A manufacturer with no eligible chassis is not a failure and starts no loop."""
    plugin = _plugin()
    monkeypatch.setattr(
        runner.Manufacturer.objects,
        "get",
        Mock(return_value=plugin.manufacturer),
    )
    _bind(monkeypatch, plugin)
    monkeypatch.setattr(runner.WirelessChassis.objects, "filter", Mock(return_value=[]))
    run = Mock()
    monkeypatch.setattr(runner.asyncio, "run", run)

    runner.run_realtime_subscriptions(17)

    run.assert_not_called()


def test_a_selected_device_narrows_the_window_to_one_chassis(monkeypatch) -> None:
    """An operator subscribing to one device must not open the whole inventory."""
    plugin = _plugin(transport="websocket")
    all_chassis = Mock()
    selected_chassis = MagicMock()
    all_chassis.filter.return_value = selected_chassis
    selected_chassis.order_by.return_value.__getitem__.return_value = [
        SimpleNamespace(api_device_id="device-1")
    ]
    monkeypatch.setattr(
        runner.Manufacturer.objects,
        "get",
        Mock(return_value=plugin.manufacturer),
    )
    _bind(monkeypatch, plugin)
    monkeypatch.setattr(
        runner.WirelessChassis.objects,
        "filter",
        Mock(return_value=all_chassis),
    )
    run = Mock()
    monkeypatch.setattr(runner.asyncio, "run", run)

    runner.run_realtime_subscriptions(17, chassis_id=27)

    all_chassis.filter.assert_called_once_with(pk=27)
    run.call_args.args[0].close()


def test_the_supervisor_reloads_the_next_fair_window_off_the_event_loop(
    monkeypatch,
    isolated_supervisor_lease,
) -> None:
    """The live supervisor receives a reload callback for later inventory windows."""
    plugin = _plugin()
    first = SimpleNamespace(api_device_id="device-1")
    second = SimpleNamespace(api_device_id="device-2")
    isolated_supervisor_lease.side_effect = [[first], [second]]
    monkeypatch.setattr(
        runner.Manufacturer.objects,
        "get",
        Mock(return_value=plugin.manufacturer),
    )
    _bind(monkeypatch, plugin)
    monkeypatch.setattr(runner.WirelessChassis.objects, "filter", Mock(return_value=Mock()))
    monkeypatch.setattr(runner, "sync_to_async", direct_sync_adapter)

    async def run_and_reload(*, items, reload_items, **_kwargs):
        assert items == [first]
        assert await reload_items() == [second]

    monkeypatch.setattr(runner.RealtimeSubscriptionSupervisor, "run", run_and_reload)

    runner.run_realtime_subscriptions(17)

    assert isolated_supervisor_lease.call_count == 2


def test_a_reload_stops_rotating_work_after_manufacturer_deactivation(
    monkeypatch,
    isolated_supervisor_lease,
) -> None:
    """A live supervisor ends without selecting another stale inventory window."""
    plugin = _plugin()
    isolated_supervisor_lease.side_effect = [[SimpleNamespace(api_device_id="device-1")]]
    monkeypatch.setattr(
        runner.Manufacturer.objects,
        "get",
        Mock(return_value=plugin.manufacturer),
    )
    _bind(monkeypatch, plugin)
    monkeypatch.setattr(runner.WirelessChassis.objects, "filter", Mock(return_value=Mock()))
    monkeypatch.setattr(runner, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(
        runner.ManufacturerActivationService,
        "is_active",
        Mock(return_value=False),
    )

    async def run_and_reload(*, reload_items, **_kwargs):
        assert await reload_items() == []

    monkeypatch.setattr(runner.RealtimeSubscriptionSupervisor, "run", run_and_reload)

    runner.run_realtime_subscriptions(17)

    assert isolated_supervisor_lease.call_count == 1


def test_an_orchestration_failure_is_contained_and_redacted(monkeypatch, caplog) -> None:
    """A failure anywhere in the round cannot escape the task boundary or leak detail."""
    secret = "private-supervisor-detail"
    plugin = _plugin()
    monkeypatch.setattr(
        runner.Manufacturer.objects,
        "get",
        Mock(return_value=plugin.manufacturer),
    )
    _bind(monkeypatch, plugin)
    monkeypatch.setattr(
        runner.WirelessChassis.objects,
        "filter",
        Mock(side_effect=RuntimeError(secret)),
    )

    runner.run_realtime_subscriptions(17)

    assert secret not in caplog.text


def test_existing_connection_tracking_is_retargeted_to_the_active_transport(
    monkeypatch,
) -> None:
    """A chassis that previously streamed over the other transport is retargeted once."""
    from micboard.models.realtime.connection import RealTimeConnection

    chassis = object()
    connection = SimpleNamespace(connection_type="websocket", save=Mock())
    monkeypatch.setattr(
        RealTimeConnection.objects,
        "get_or_create",
        Mock(return_value=(connection, False)),
    )
    mark = Mock()
    monkeypatch.setattr(runner, "mark_connecting", mark)

    assert runner._track_connection(chassis, "sse") is connection

    assert connection.connection_type == "sse"
    connection.save.assert_called_once_with(update_fields=["connection_type", "updated_at"])
    mark.assert_called_once_with(connection)

    connection.save.reset_mock()
    runner._track_connection(chassis, "sse")
    connection.save.assert_not_called()


def test_a_subscription_round_delegates_updates_to_the_shared_lifecycle(monkeypatch) -> None:
    """Every transport persists and broadcasts through one lifecycle entry point."""
    process = AsyncMock()
    monkeypatch.setattr(
        RealtimeSubscriptionLifecycleService,
        "process_update",
        process,
    )
    monkeypatch.setattr(runner, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(runner, "_track_connection", Mock(return_value=Mock()))
    monkeypatch.setattr(runner, "mark_stopped", Mock())
    monkeypatch.setattr(runner, "received_message", Mock())
    chassis = SimpleNamespace(pk=28, api_device_id="device-1")

    async def deliver(_chassis, callback):
        await callback({"id": "device-1"})

    plugin = _plugin(transport="websocket", subscribe_to_chassis=AsyncMock(side_effect=deliver))

    asyncio.run(runner._subscribe_chassis(plugin, "websocket", chassis))

    process.assert_awaited_once_with(
        plugin=plugin,
        data={"id": "device-1"},
        transport="websocket",
    )


def test_a_round_stops_before_the_stream_when_the_manufacturer_deactivates(
    monkeypatch,
) -> None:
    """Activation is rechecked after tracking setup, so a deactivation stops the round."""
    connection = object()
    monkeypatch.setattr(runner, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(runner, "_track_connection", Mock(return_value=connection))
    monkeypatch.setattr(
        runner.ManufacturerActivationService,
        "is_active",
        Mock(return_value=False),
    )
    stopped = Mock()
    monkeypatch.setattr(runner, "mark_stopped", stopped)
    plugin = _plugin()
    chassis = SimpleNamespace(pk=28, api_device_id="device-1")

    asyncio.run(runner._subscribe_chassis(plugin, "sse", chassis))

    plugin.subscribe_to_chassis.assert_not_awaited()
    stopped.assert_called_once_with(connection)


def test_a_failure_before_tracking_exists_is_still_contained(monkeypatch, caplog) -> None:
    """Connection tracking can fail, and that cannot abort the supervisor or leak detail."""
    secret = "private-tracking-detail"
    monkeypatch.setattr(runner, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(runner, "_track_connection", Mock(side_effect=RuntimeError(secret)))
    plugin = _plugin()

    asyncio.run(
        runner._subscribe_chassis(plugin, "sse", SimpleNamespace(pk=28, api_device_id="one"))
    )

    plugin.subscribe_to_chassis.assert_not_awaited()
    assert secret not in caplog.text


def test_realtime_logs_exclude_vendor_and_device_sentinels(monkeypatch, caplog) -> None:
    """Realtime logs retain numeric model context without vendor-controlled identifiers."""
    manufacturer_code = "secret-vendor-code"
    manufacturer_name = "secret vendor display name"
    device_id = "secret-device-identifier"
    chassis_name = "secret chassis display name"
    transport_secret = "secret transport credential"
    caplog.set_level("DEBUG")

    plugin = _plugin(
        manufacturer=SimpleNamespace(pk=41, code=manufacturer_code, name=manufacturer_name),
        subscribe_to_chassis=AsyncMock(side_effect=RuntimeError(transport_secret)),
        transform_device_data=Mock(return_value=None),
    )
    chassis = SimpleNamespace(pk=42, name=chassis_name, api_device_id=device_id)
    monkeypatch.setattr(runner, "sync_to_async", direct_sync_adapter)
    monkeypatch.setattr(runner, "_track_connection", Mock(return_value=None))

    asyncio.run(runner._subscribe_chassis(plugin, "sse", chassis))
    asyncio.run(
        RealtimeSubscriptionLifecycleService.process_update(
            plugin=plugin,
            data={},
            transport="sse",
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
