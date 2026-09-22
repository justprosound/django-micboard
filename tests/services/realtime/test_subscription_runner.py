"""How one realtime subscription run is orchestrated.

A manufacturer's integration streams over exactly one transport, and which one is a
property of the integration rather than an operator's choice. One runner therefore drives
both: it asks the plugin which transport it speaks, leases that transport, selects a bounded
chassis window, and hands each chassis back to the plugin to connect.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from micboard.services.realtime.subscription_runner import run_realtime_subscriptions
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory

pytestmark = pytest.mark.django_db(transaction=True)


class _StreamingPlugin:
    """A plugin that records the chassis it was asked to stream."""

    def __init__(self, manufacturer: Any, transport: str = "sse") -> None:
        self.manufacturer = manufacturer
        self._transport = transport
        self.subscribed: list[Any] = []

    @property
    def realtime_transport(self) -> str:
        return self._transport

    async def subscribe_to_chassis(self, chassis: Any, callback: Any) -> None:
        self.subscribed.append(chassis)


def _run_serially(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the supervisor's bounded loop with one pass over its items."""

    async def run(*, items, subscribe, **_kwargs):
        for item in items:
            await subscribe(item)

    monkeypatch.setattr(
        "micboard.services.realtime.subscription_runner.RealtimeSubscriptionSupervisor.run",
        run,
    )


def test_the_runner_streams_each_selected_chassis_through_the_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every chassis in the selected window reaches the integration that owns it."""
    manufacturer = ManufacturerFactory(code="vendor")
    first = WirelessChassisFactory(manufacturer=manufacturer, status="online")
    second = WirelessChassisFactory(manufacturer=manufacturer, status="online")
    plugin = _StreamingPlugin(manufacturer)
    monkeypatch.setattr(
        "micboard.services.realtime.subscription_runner.build_manufacturer_plugin",
        Mock(return_value=plugin),
    )
    _run_serially(monkeypatch)

    run_realtime_subscriptions(manufacturer.pk)

    assert [chassis.pk for chassis in plugin.subscribed] == [first.pk, second.pk]


def test_the_runner_leases_the_transport_the_plugin_declares(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The singleton lease is per transport, so it must name the plugin's own transport."""
    manufacturer = ManufacturerFactory(code="vendor")
    WirelessChassisFactory(manufacturer=manufacturer, status="online")
    plugin = _StreamingPlugin(manufacturer, transport="websocket")
    monkeypatch.setattr(
        "micboard.services.realtime.subscription_runner.build_manufacturer_plugin",
        Mock(return_value=plugin),
    )
    acquire = Mock(return_value=Mock())
    monkeypatch.setattr(
        "micboard.services.realtime.subscription_runner.RealtimeSubscriptionSupervisor.acquire",
        acquire,
    )
    _run_serially(monkeypatch)

    run_realtime_subscriptions(manufacturer.pk)

    acquire.assert_called_once_with(transport="websocket", scope=manufacturer.pk)


def test_an_integration_without_a_stream_does_no_outbound_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plugin that declares no transport must not take a lease or open a connection."""
    manufacturer = ManufacturerFactory(code="vendor")
    WirelessChassisFactory(manufacturer=manufacturer, status="online")
    plugin = _StreamingPlugin(manufacturer)
    plugin._transport = None  # type: ignore[assignment]
    monkeypatch.setattr(
        "micboard.services.realtime.subscription_runner.build_manufacturer_plugin",
        Mock(return_value=plugin),
    )
    acquire = Mock()
    monkeypatch.setattr(
        "micboard.services.realtime.subscription_runner.RealtimeSubscriptionSupervisor.acquire",
        acquire,
    )

    run_realtime_subscriptions(manufacturer.pk)

    acquire.assert_not_called()
    assert plugin.subscribed == []


def test_connection_tracking_records_the_transport_in_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Operators read the connection row to see how a chassis is being streamed."""
    from micboard.models.realtime.connection import RealTimeConnection

    manufacturer = ManufacturerFactory(code="vendor")
    chassis = WirelessChassisFactory(manufacturer=manufacturer, status="online")
    plugin = _StreamingPlugin(manufacturer, transport="websocket")
    monkeypatch.setattr(
        "micboard.services.realtime.subscription_runner.build_manufacturer_plugin",
        Mock(return_value=plugin),
    )
    _run_serially(monkeypatch)

    run_realtime_subscriptions(manufacturer.pk)

    connection = RealTimeConnection.objects.get(chassis=chassis)
    assert connection.connection_type == "websocket"


def test_a_stream_failure_is_recorded_without_leaking_its_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A vendor transport error marks the connection without publishing its message."""
    from micboard.models.realtime.connection import RealTimeConnection

    manufacturer = ManufacturerFactory(code="vendor")
    chassis = WirelessChassisFactory(manufacturer=manufacturer, status="online")
    plugin = _StreamingPlugin(manufacturer)
    plugin.subscribe_to_chassis = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError("bearer token nine-nine-nine")
    )
    monkeypatch.setattr(
        "micboard.services.realtime.subscription_runner.build_manufacturer_plugin",
        Mock(return_value=plugin),
    )
    _run_serially(monkeypatch)

    run_realtime_subscriptions(manufacturer.pk)

    connection = RealTimeConnection.objects.get(chassis=chassis)
    assert connection.status == "error"
    assert "nine-nine-nine" not in connection.error_message
