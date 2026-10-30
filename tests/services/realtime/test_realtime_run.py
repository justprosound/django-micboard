"""What one realtime run does, observed through its entry point.

Each test drives `run_realtime_subscriptions` with a fake plugin and real database rows, and
asserts only what an operator could see afterwards: what the plugin was asked to stream, what
the connection rows say, whether the transport lease was taken, and what reached the logs. The
supervisor's rotation loop is real; a fake plugin ends a run by deactivating its manufacturer,
which the supervisor notices when it reloads the next window.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import Mock

from django.core.cache import caches

import pytest
from asgiref.sync import sync_to_async

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.models.realtime.connection import RealTimeConnection
from micboard.services.realtime.subscription_runner import run_realtime_subscriptions
from micboard.services.realtime.subscription_supervisor import RealtimeSubscriptionSupervisor
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db(transaction=True)

_PLUGIN_BUILDER = "micboard.services.realtime.subscription_runner.build_manufacturer_plugin"


class _FakePlugin:
    """A plugin whose stream is a coroutine the test supplies."""

    def __init__(
        self,
        manufacturer: Manufacturer,
        *,
        transport: str | None = "sse",
        stream: Callable[[_FakePlugin, WirelessChassis], Awaitable[None]] | None = None,
    ) -> None:
        self.manufacturer = manufacturer
        self.realtime_transport = transport
        self.subscribed: list[int] = []
        self._stream = stream

    async def subscribe_to_chassis(self, chassis: WirelessChassis, callback: Any) -> None:
        self.subscribed.append(chassis.pk)
        if self._stream is not None:
            await self._stream(self, chassis)

    async def deactivate_manufacturer(self) -> None:
        """End the run: the supervisor stops rotating once the manufacturer is inactive."""
        await sync_to_async(
            Manufacturer.objects.filter(pk=self.manufacturer.pk).update,
            thread_sensitive=True,
        )(is_active=False)


@pytest.fixture(autouse=True)
def _isolated_run(settings: Any) -> None:
    """Start each run with no lease, no rotation cursor and no reconnect delay."""
    caches["default"].clear()
    settings.MICBOARD_REALTIME_RECONNECT_DELAY_SECONDS = 0


def _use(monkeypatch: pytest.MonkeyPatch, plugin: _FakePlugin) -> Mock:
    build = Mock(return_value=plugin)
    monkeypatch.setattr(_PLUGIN_BUILDER, build)
    return build


def _lease_is_held(transport: str, manufacturer: Manufacturer) -> bool:
    """Whether a new run could not take the lease. Probing acquires it, so call this last."""
    return (
        RealtimeSubscriptionSupervisor.acquire(transport=transport, scope=manufacturer.pk) is None
    )


async def _end_after_streaming(plugin: _FakePlugin, chassis: WirelessChassis) -> None:
    await plugin.deactivate_manufacturer()


def test_an_inactive_manufacturer_is_not_streamed(monkeypatch: pytest.MonkeyPatch) -> None:
    manufacturer = ManufacturerFactory(code="vendor", is_active=False)
    WirelessChassisFactory(manufacturer=manufacturer, status="online")
    build = _use(monkeypatch, _FakePlugin(manufacturer))

    run_realtime_subscriptions(manufacturer.pk)

    build.assert_not_called()
    assert RealTimeConnection.objects.count() == 0
    assert not _lease_is_held("sse", manufacturer)


def test_a_missing_manufacturer_is_not_streamed(monkeypatch: pytest.MonkeyPatch) -> None:
    manufacturer = ManufacturerFactory(code="vendor")
    build = _use(monkeypatch, _FakePlugin(manufacturer))

    run_realtime_subscriptions(manufacturer.pk + 1000)

    build.assert_not_called()
    assert RealTimeConnection.objects.count() == 0


def test_an_integration_that_does_not_stream_takes_no_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manufacturer = ManufacturerFactory(code="vendor")
    WirelessChassisFactory(manufacturer=manufacturer, status="online")
    plugin = _FakePlugin(manufacturer, transport=None)
    _use(monkeypatch, plugin)

    run_realtime_subscriptions(manufacturer.pk)

    assert plugin.subscribed == []
    assert RealTimeConnection.objects.count() == 0
    assert not _lease_is_held("sse", manufacturer)
    assert not _lease_is_held("websocket", manufacturer)


def test_no_eligible_chassis_takes_no_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leases expire rather than being released, so an empty inventory must not take one."""
    manufacturer = ManufacturerFactory(code="vendor")
    WirelessChassisFactory(manufacturer=manufacturer, status="offline")
    plugin = _FakePlugin(manufacturer)
    _use(monkeypatch, plugin)

    run_realtime_subscriptions(manufacturer.pk)

    assert plugin.subscribed == []
    assert RealTimeConnection.objects.count() == 0
    assert not _lease_is_held("sse", manufacturer)


def test_a_held_lease_means_no_chassis_is_streamed(monkeypatch: pytest.MonkeyPatch) -> None:
    manufacturer = ManufacturerFactory(code="vendor")
    WirelessChassisFactory(manufacturer=manufacturer, status="online")
    plugin = _FakePlugin(manufacturer)
    _use(monkeypatch, plugin)
    assert RealtimeSubscriptionSupervisor.acquire(transport="sse", scope=manufacturer.pk)

    run_realtime_subscriptions(manufacturer.pk)

    assert plugin.subscribed == []
    assert RealTimeConnection.objects.count() == 0


def test_a_window_that_empties_after_the_lease_is_taken_streams_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Another process can take the chassis offline between the eligibility check and selection."""
    manufacturer = ManufacturerFactory(code="vendor")
    chassis = WirelessChassisFactory(manufacturer=manufacturer, status="online")
    plugin = _FakePlugin(manufacturer)
    _use(monkeypatch, plugin)
    acquire = RealtimeSubscriptionSupervisor.acquire

    def acquire_then_lose_the_chassis(**kwargs: Any) -> Any:
        lease = acquire(**kwargs)
        WirelessChassis.objects.filter(pk=chassis.pk).update(status="offline")
        return lease

    monkeypatch.setattr(RealtimeSubscriptionSupervisor, "acquire", acquire_then_lose_the_chassis)

    run_realtime_subscriptions(manufacturer.pk)

    assert plugin.subscribed == []
    assert RealTimeConnection.objects.count() == 0
    assert _lease_is_held("sse", manufacturer)


def test_a_normal_run_streams_each_chassis_and_leaves_its_connection_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manufacturer = ManufacturerFactory(code="vendor")
    first = WirelessChassisFactory(manufacturer=manufacturer, status="online")
    second = WirelessChassisFactory(manufacturer=manufacturer, status="degraded")
    WirelessChassisFactory(manufacturer=manufacturer, status="offline")
    streamed_while: dict[int, str] = {}

    async def stream(plugin: _FakePlugin, chassis: WirelessChassis) -> None:
        row = await sync_to_async(RealTimeConnection.objects.get, thread_sensitive=True)(
            chassis=chassis
        )
        streamed_while[chassis.pk] = row.status
        if len(plugin.subscribed) == 2:
            await plugin.deactivate_manufacturer()

    plugin = _FakePlugin(manufacturer, transport="websocket", stream=stream)
    _use(monkeypatch, plugin)

    run_realtime_subscriptions(manufacturer.pk)

    assert sorted(plugin.subscribed) == sorted([first.pk, second.pk])
    assert streamed_while == {first.pk: "connecting", second.pk: "connecting"}
    rows = RealTimeConnection.objects.all()
    assert {row.chassis_id for row in rows} == {first.pk, second.pk}
    assert {row.status for row in rows} == {"stopped"}
    assert {row.connection_type for row in rows} == {"websocket"}
    assert _lease_is_held("websocket", manufacturer)


def test_a_selected_chassis_narrows_the_run_to_that_chassis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manufacturer = ManufacturerFactory(code="vendor")
    WirelessChassisFactory(manufacturer=manufacturer, status="online")
    chosen = WirelessChassisFactory(manufacturer=manufacturer, status="online")
    plugin = _FakePlugin(manufacturer, stream=_end_after_streaming)
    _use(monkeypatch, plugin)

    run_realtime_subscriptions(manufacturer.pk, chassis_id=chosen.pk)

    assert plugin.subscribed == [chosen.pk]


def test_a_stream_that_fails_marks_only_its_own_connection_as_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manufacturer = ManufacturerFactory(code="vendor")
    first = WirelessChassisFactory(manufacturer=manufacturer, status="online")
    second = WirelessChassisFactory(manufacturer=manufacturer, status="online")

    async def stream(plugin: _FakePlugin, chassis: WirelessChassis) -> None:
        if chassis.pk == first.pk:
            raise RuntimeError("bearer token nine-nine-nine")
        await plugin.deactivate_manufacturer()

    _use(monkeypatch, _FakePlugin(manufacturer, stream=stream))

    run_realtime_subscriptions(manufacturer.pk)

    assert RealTimeConnection.objects.get(chassis=first).status == "error"
    assert RealTimeConnection.objects.get(chassis=second).status == "stopped"


def test_an_unexpected_crash_is_contained_and_redacted(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    manufacturer = ManufacturerFactory(code="vendor")
    WirelessChassisFactory(manufacturer=manufacturer, status="online")
    monkeypatch.setattr(_PLUGIN_BUILDER, Mock(side_effect=RuntimeError("private-detail")))

    run_realtime_subscriptions(manufacturer.pk)

    assert "private-detail" not in caplog.text
    assert f"manufacturer ID {manufacturer.pk}" in caplog.text
    assert RealTimeConnection.objects.count() == 0


def test_cancelling_a_chassis_while_it_connects_leaves_its_connection_stopped(
    monkeypatch: pytest.MonkeyPatch, settings: Any
) -> None:
    """The supervisor's rotation timeout cancels a stream that never finishes connecting."""
    settings.MICBOARD_REALTIME_ROTATION_SECONDS = 1
    manufacturer = ManufacturerFactory(code="vendor")
    chassis = WirelessChassisFactory(manufacturer=manufacturer, status="online")
    seen: list[str] = []

    async def stream(plugin: _FakePlugin, streaming: WirelessChassis) -> None:
        row = await sync_to_async(RealTimeConnection.objects.get, thread_sensitive=True)(
            chassis=streaming
        )
        seen.append(row.status)
        if len(plugin.subscribed) > 1:
            await plugin.deactivate_manufacturer()
            return
        await asyncio.sleep(3600)

    _use(monkeypatch, _FakePlugin(manufacturer, stream=stream))

    run_realtime_subscriptions(manufacturer.pk)

    assert seen[0] == "connecting"
    assert RealTimeConnection.objects.get(chassis=chassis).status == "stopped"
