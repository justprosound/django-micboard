"""Service-level coverage for real-time connection health management."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import patch

from django.http import HttpRequest, HttpResponse
from django.test import override_settings
from django.utils import timezone

import pytest

from micboard.middleware import ConnectionHealthMiddleware
from micboard.services.monitoring.connection import ConnectionHealthService
from tests.async_utils import run_async_with_heartbeat
from tests.factories.discovery import ManufacturerFactory
from tests.factories.hardware import WirelessChassisFactory
from tests.factories.realtime import RealTimeConnectionFactory


@pytest.fixture(autouse=True)
def isolate_chassis_lifecycle():
    """Keep service tests independent of manufacturer and task transports."""
    with (
        override_settings(TESTING=True),
        patch(
            "micboard.services.manufacturer.plugin_registry.PluginRegistry.get_plugin",
            return_value=None,
        ),
    ):
        yield


@pytest.mark.django_db
def test_create_and_update_connection_statuses() -> None:
    """Status transitions update timestamps and reset or increment errors."""
    chassis = WirelessChassisFactory()
    connected_at = timezone.now()
    with patch("micboard.services.monitoring.connection.now", return_value=connected_at):
        connection = ConnectionHealthService.create_connection(
            chassis=chassis,
            connection_type="websocket",
            status="connected",
        )

    assert connection.connected_at == connected_at

    connection.error_count = 4
    with patch("micboard.services.monitoring.connection.now", return_value=connected_at):
        ConnectionHealthService.update_connection_status(
            connection=connection,
            status="connected",
        )
    assert connection.last_message_at == connected_at
    assert connection.error_count == 0

    errored_at = connected_at + timedelta(minutes=1)
    with patch("micboard.services.monitoring.connection.now", return_value=errored_at):
        ConnectionHealthService.update_connection_status(connection=connection, status="error")
    assert connection.disconnected_at == errored_at
    assert connection.error_count == 1

    ConnectionHealthService.update_connection_status(
        connection=connection,
        status="disconnected",
    )
    assert connection.error_count == 1


@pytest.mark.django_db
def test_heartbeat_and_error_details_are_persisted() -> None:
    """Health observations update only their focused connection fields."""
    connection = RealTimeConnectionFactory(error_count=2)
    heartbeat_at = timezone.now()

    with patch("micboard.services.monitoring.connection.now", return_value=heartbeat_at):
        ConnectionHealthService.record_heartbeat(connection=connection)
    ConnectionHealthService.record_error(
        connection=connection,
        error_message="socket closed",
    )

    connection.refresh_from_db()
    assert connection.last_message_at == heartbeat_at
    assert connection.error_message == "socket closed"
    assert connection.error_count == 3


@pytest.mark.django_db
def test_health_checks_and_unhealthy_query_cover_missing_or_stale_heartbeats() -> None:
    """Connected rows without a recent heartbeat are consistently unhealthy."""
    check_time = timezone.now()
    healthy = RealTimeConnectionFactory(
        status="connected",
        last_message_at=check_time - timedelta(seconds=10),
    )
    stale = RealTimeConnectionFactory(
        status="connected",
        last_message_at=check_time - timedelta(minutes=5),
    )
    missing = RealTimeConnectionFactory(status="connected", last_message_at=None)
    disconnected = RealTimeConnectionFactory(status="disconnected", last_message_at=check_time)

    with patch("micboard.services.monitoring.connection.now", return_value=check_time):
        assert ConnectionHealthService.is_healthy(connection=healthy)
        assert not ConnectionHealthService.is_healthy(connection=stale)
        assert not ConnectionHealthService.is_healthy(connection=missing)
        assert not ConnectionHealthService.is_healthy(connection=disconnected)
        unhealthy = set(ConnectionHealthService.get_unhealthy_connections())

    assert unhealthy == {stale, missing}
    assert set(ConnectionHealthService.get_active_connections()) == {healthy, stale, missing}


@pytest.mark.django_db
def test_connection_health_middleware_has_constant_relation_loading(
    django_assert_num_queries,
) -> None:
    """API health checks load unhealthy chassis manufacturers in one query."""
    RealTimeConnectionFactory(
        status="connected",
        last_message_at=None,
    )
    RealTimeConnectionFactory(
        status="connected",
        last_message_at=timezone.now() - timedelta(minutes=5),
    )
    request = HttpRequest()
    request.path = "/api/status/"
    middleware = ConnectionHealthMiddleware(lambda _request: HttpResponse())

    with django_assert_num_queries(1):
        middleware.process_request(request)

    assert len(request.unhealthy_connections) == 2  # type: ignore[attr-defined]
    assert all(
        connection.chassis.manufacturer.code
        for connection in request.unhealthy_connections  # type: ignore[attr-defined]
    )


@pytest.mark.django_db
def test_manufacturer_query_and_stale_cleanup() -> None:
    """Manufacturer filters are ordered and only old disconnected rows are deleted."""
    manufacturer = ManufacturerFactory(code="query-vendor")
    matching = RealTimeConnectionFactory(
        chassis=WirelessChassisFactory(manufacturer=manufacturer),
    )
    RealTimeConnectionFactory()
    cutoff = timezone.now() - timedelta(hours=24)
    old = RealTimeConnectionFactory(
        status="disconnected",
        disconnected_at=cutoff - timedelta(hours=1),
    )
    recent = RealTimeConnectionFactory(
        status="disconnected",
        disconnected_at=cutoff + timedelta(hours=1),
    )

    assert list(
        ConnectionHealthService.get_connections_by_manufacturer(manufacturer_code="query-vendor")
    ) == [matching]
    with patch(
        "micboard.services.monitoring.connection.now", return_value=cutoff + timedelta(days=1)
    ):
        deleted = ConnectionHealthService.cleanup_stale_connections(max_age_hours=24)

    assert deleted == 1
    assert not type(old).objects.filter(pk=old.pk).exists()
    assert type(recent).objects.filter(pk=recent.pk).exists()


@pytest.mark.django_db
def test_connection_uptime_handles_live_closed_and_incomplete_rows() -> None:
    """Uptime uses the current clock only for active connections."""
    started_at = timezone.now() - timedelta(hours=2)
    connected = RealTimeConnectionFactory(status="connected", connected_at=started_at)
    closed = RealTimeConnectionFactory(
        status="disconnected",
        connected_at=started_at,
        disconnected_at=started_at + timedelta(minutes=30),
    )
    incomplete = RealTimeConnectionFactory(status="disconnected", connected_at=started_at)
    never_connected = RealTimeConnectionFactory(connected_at=None)

    with patch(
        "micboard.services.monitoring.connection.now",
        return_value=started_at + timedelta(hours=2),
    ):
        assert ConnectionHealthService.get_connection_uptime(connection=connected) == timedelta(
            hours=2
        )
    assert ConnectionHealthService.get_connection_uptime(connection=closed) == timedelta(minutes=30)
    assert ConnectionHealthService.get_connection_uptime(connection=incomplete) is None
    assert ConnectionHealthService.get_connection_uptime(connection=never_connected) is None


@pytest.mark.django_db
def test_connection_stats_and_error_reset(django_assert_num_queries) -> None:
    """Aggregate stats use fixed queries regardless of manufacturer count."""
    manufacturer = ManufacturerFactory(code="stats-vendor")
    first = RealTimeConnectionFactory(
        chassis=WirelessChassisFactory(manufacturer=manufacturer),
        status="connected",
        error_count=1,
        error_message="first",
        last_error_at=timezone.now(),
    )
    RealTimeConnectionFactory(
        chassis=WirelessChassisFactory(manufacturer=manufacturer),
        status="error",
        error_count=3,
    )
    other_manufacturer = ManufacturerFactory(code="other-stats-vendor")
    RealTimeConnectionFactory(
        chassis=WirelessChassisFactory(manufacturer=other_manufacturer),
        status="disconnected",
        error_count=2,
    )

    with django_assert_num_queries(2):
        stats = ConnectionHealthService.get_connection_stats()

    assert stats == {
        "total_connections": 3,
        "active_connections": 1,
        "error_connections": 1,
        "avg_error_count": 2.0,
        "by_manufacturer": {"other-stats-vendor": 1, "stats-vendor": 2},
    }

    reset = ConnectionHealthService.reset_connection_errors(connection=first)
    assert reset.error_count == 0
    assert reset.error_message == ""
    assert reset.last_error_at is None


@pytest.mark.django_db
def test_empty_connection_stats() -> None:
    """An empty connection table reports a null average and no manufacturers."""
    assert ConnectionHealthService.get_connection_stats() == {
        "total_connections": 0,
        "active_connections": 0,
        "error_connections": 0,
        "avg_error_count": None,
        "by_manufacturer": {},
    }


def _direct_async_adapter(function, **_kwargs):
    async def call(*args, **kwargs):
        return function(*args, **kwargs)

    return call


def test_async_connection_helpers_delegate_to_sync_services() -> None:
    """Async adapters preserve arguments and return values without duplicate logic."""
    connection = object()
    unhealthy = [object()]
    with (
        patch("asgiref.sync.sync_to_async", side_effect=_direct_async_adapter),
        patch.object(
            ConnectionHealthService,
            "get_unhealthy_connections",
            return_value=unhealthy,
        ) as get_unhealthy,
        patch.object(ConnectionHealthService, "record_heartbeat") as record_heartbeat,
        patch.object(ConnectionHealthService, "is_healthy", return_value=True) as is_healthy,
    ):
        assert (
            asyncio.run(
                ConnectionHealthService.aget_unhealthy_connections(heartbeat_timeout_seconds=15)
            )
            == unhealthy
        )
        asyncio.run(ConnectionHealthService.arecord_heartbeat(connection=connection))
        assert asyncio.run(
            ConnectionHealthService.ais_healthy(
                connection=connection,
                heartbeat_timeout_seconds=15,
            )
        )

    get_unhealthy.assert_called_once_with(heartbeat_timeout_seconds=15)
    record_heartbeat.assert_called_once_with(connection=connection)
    is_healthy.assert_called_once_with(connection=connection, heartbeat_timeout_seconds=15)


@pytest.mark.django_db(transaction=True)
def test_async_unhealthy_query_materializes_results_before_returning() -> None:
    """Connection iteration and selected relations remain safe in an event loop."""
    manufacturer = ManufacturerFactory(code="async-health-vendor")
    stale = RealTimeConnectionFactory(
        chassis=WirelessChassisFactory(manufacturer=manufacturer),
        status="connected",
        last_message_at=None,
    )
    RealTimeConnectionFactory(status="disconnected")

    async def evaluate_results() -> tuple[list[int], list[str]]:
        connections = await ConnectionHealthService.aget_unhealthy_connections()
        assert isinstance(connections, list)
        return (
            [connection.pk for connection in connections],
            [connection.chassis.manufacturer.code for connection in connections],
        )

    connection_ids, manufacturer_codes = run_async_with_heartbeat(evaluate_results())

    assert connection_ids == [stale.pk]
    assert manufacturer_codes == ["async-health-vendor"]
