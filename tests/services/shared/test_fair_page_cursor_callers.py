"""Each fair-page cursor caller keeps its own key, timeout and cache alias, and survives an outage."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import override_settings

import pytest

from micboard.services.chargers import polling_cache
from micboard.services.chargers.polling_cache import ChargerPollingCacheAdapter
from micboard.services.monitoring import alert_fanout_service, poll_alert_service
from micboard.services.monitoring.alert_fanout_service import AlertFanoutService
from micboard.services.monitoring.poll_alert_service import PollAlertService
from micboard.services.notification import device_broadcast_service
from micboard.services.notification.device_broadcast_service import DeviceSnapshotBroadcastService
from micboard.services.realtime import subscription_supervisor
from micboard.services.realtime.subscription_supervisor import RealtimeSubscriptionSupervisor
from micboard.services.shared import fair_page_cursor
from micboard.services.sync import discovery_source_cursor_service
from micboard.services.sync.discovery_source_cursor_service import (
    DiscoverySource,
    DiscoverySourceCursorService,
)
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory

WEEK = 7 * 24 * 60 * 60


@pytest.mark.parametrize(
    ("spec", "timeout"),
    [
        (alert_fanout_service._ASSIGNMENT_CURSOR, WEEK),
        (alert_fanout_service._RECIPIENT_CURSOR, WEEK),
        (poll_alert_service._SCAN_CURSOR, WEEK),
        (poll_alert_service._SCOPE_CURSOR, WEEK),
        (subscription_supervisor._SELECTION_CURSOR, 30 * 24 * 60 * 60),
        (discovery_source_cursor_service._SOURCE_CURSOR, WEEK),
        (device_broadcast_service._BROADCAST_CURSOR, WEEK),
        (polling_cache._CURSOR, WEEK),
    ],
)
def test_each_caller_keeps_its_cursor_timeout(spec: Any, timeout: int) -> None:
    backend = MagicMock()
    handler = MagicMock()
    handler.__getitem__.return_value = backend

    with patch.object(fair_page_cursor, "caches", handler):
        fair_page_cursor.write_cursor(spec, "k", spec.fresh())

    backend.set.assert_called_once()
    assert backend.set.call_args.kwargs == {"timeout": timeout}


def test_each_caller_keeps_its_cursor_key() -> None:
    manufacturer = SimpleNamespace(pk=7, code="shure")

    assert (
        AlertFanoutService._assignment_cursor_key(unit_id=3, scope="s")
        == "micboard:alert-fanout:v1:assignment:s:3"
    )
    assert (
        AlertFanoutService._recipient_cursor_key(unit_id=3, scope="s")
        == "micboard:alert-fanout:v1:recipient:s:3"
    )
    assert PollAlertService._cursor_key(7) == "micboard:poll-alert-cursor:v1:7"
    assert PollAlertService._scope_cursor_key(7) == "micboard:poll-alert-scope:v1:7"
    assert (
        RealtimeSubscriptionSupervisor._selection_cursor_key(transport="sse", scope=7)
        == "micboard:realtime-selection-cursor:v1:sse:7"
    )
    assert (
        DeviceSnapshotBroadcastService._cursor_key(7, namespace="n")
        == "micboard:device-broadcast-cursor:v1:n:7"
    )
    assert ChargerPollingCacheAdapter.cursor_key(manufacturer) == "micboard:charger-poll:v1:7:shure"
    assert DiscoverySourceCursorService._cursor_key(manufacturer, group="g", source="s").startswith(
        "micboard:discovery-source-cursor:v1:"
    )


@pytest.mark.django_db
@override_settings(MICBOARD_REALTIME_CACHE_ALIAS="realtime")
def test_supervisor_reads_and_writes_its_cursor_on_the_realtime_alias() -> None:
    manufacturer = ManufacturerFactory(code=f"alias-{uuid4().hex[:8]}")
    WirelessChassisFactory(manufacturer=manufacturer, status="online")
    backend = MagicMock()
    backend.get.return_value = None
    handler = MagicMock()
    handler.__getitem__.return_value = backend

    with patch.object(fair_page_cursor, "caches", handler):
        selected = RealtimeSubscriptionSupervisor.select_fair_queryset_batch(
            queryset=manufacturer.wirelesschassis_set.filter(status="online"),
            transport="sse",
            scope=manufacturer.pk,
            limit=2,
        )

    assert len(selected) == 1
    assert [call.args for call in handler.__getitem__.call_args_list] == [("realtime",)] * 2
    backend.get.assert_called_once_with(
        f"micboard:realtime-selection-cursor:v1:sse:{manufacturer.pk}"
    )
    assert backend.set.call_args.kwargs == {"timeout": 30 * 24 * 60 * 60}


@pytest.fixture
def broken_cache(caplog: pytest.LogCaptureFixture):
    """Make every cursor read, write and delete fail with a credential-bearing error."""
    secret = "redis://operator:private@example.test"
    backend = MagicMock()
    backend.get.side_effect = RuntimeError(secret)
    backend.set.side_effect = RuntimeError(secret)
    backend.delete.side_effect = RuntimeError(secret)
    handler = MagicMock()
    handler.__getitem__.return_value = backend
    with patch.object(fair_page_cursor, "caches", handler), caplog.at_level("ERROR"):
        yield backend
    assert secret not in caplog.text


@pytest.mark.django_db
def test_supervisor_selection_survives_a_cache_outage(broken_cache: MagicMock) -> None:
    manufacturer = ManufacturerFactory(code=f"outage-{uuid4().hex[:8]}")
    chassis = [WirelessChassisFactory(manufacturer=manufacturer, status="online") for _ in range(3)]

    selected = RealtimeSubscriptionSupervisor.select_fair_queryset_batch(
        queryset=manufacturer.wirelesschassis_set.filter(status="online"),
        transport="sse",
        scope=manufacturer.pk,
        limit=2,
    )

    assert [row.pk for row in selected] == [row.pk for row in chassis[:2]]
    broken_cache.set.assert_called_once()


@pytest.mark.django_db
def test_discovery_source_pages_survive_a_cache_outage(broken_cache: MagicMock) -> None:
    manufacturer = ManufacturerFactory(code=f"disc-{uuid4().hex[:8]}")
    for index in range(3):
        WirelessChassisFactory(manufacturer=manufacturer, ip=f"192.0.2.{10 + index}")
    source = DiscoverySource(
        name="chassis",
        queryset=manufacturer.wirelesschassis_set.all(),
        value_field="ip",
    )

    page = DiscoverySourceCursorService.rotating_page(
        manufacturer,
        group="group",
        source=source,
        limit=2,
    )

    assert page.values == ["192.0.2.10", "192.0.2.11"]
    assert page.sources_complete is False
    broken_cache.set.assert_called_once()


def test_charger_cursor_adapter_survives_a_cache_outage(broken_cache: MagicMock) -> None:
    manufacturer = SimpleNamespace(pk=7, code="shure")

    cursor = ChargerPollingCacheAdapter.read_cursor(manufacturer)
    ChargerPollingCacheAdapter.write_cursor(manufacturer, cursor)
    ChargerPollingCacheAdapter.clear_cursor(manufacturer)

    assert cursor.next_offset == 0
    assert cursor.stations == []
    broken_cache.delete.assert_called_once()
