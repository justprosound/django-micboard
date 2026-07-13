"""Focused behavior tests for maintenance and monitoring task wrappers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, Mock, call, patch

from micboard.tasks.maintenance import charger as charger_tasks
from micboard.tasks.monitoring import health as health_tasks


def test_api_health_check_persists_caches_and_broadcasts_result() -> None:
    """A successful API probe must publish the same health snapshot everywhere."""
    manufacturer = Mock(code="shure")
    health_status = {
        "status": "healthy",
        "response_time": 0.125,
        "error": "",
        "firmware": "1.2.3",
    }
    client = Mock()
    client.check_health.return_value = health_status
    plugin = Mock()
    plugin.get_client.return_value = client
    plugin_class = Mock(return_value=plugin)

    with (
        patch.object(
            health_tasks.Manufacturer.objects,
            "get",
            return_value=manufacturer,
        ) as get_manufacturer,
        patch.object(
            health_tasks,
            "get_manufacturer_plugin",
            return_value=plugin_class,
        ) as get_plugin,
        patch.object(health_tasks.APIHealthLog.objects, "create") as create_log,
        patch.object(health_tasks.cache, "set") as cache_set,
        patch.object(
            health_tasks.BroadcastService,
            "broadcast_api_health",
        ) as broadcast,
    ):
        health_tasks.check_manufacturer_api_health(17)

    get_manufacturer.assert_called_once_with(pk=17)
    get_plugin.assert_called_once_with("shure")
    plugin_class.assert_called_once_with(manufacturer)
    create_log.assert_called_once_with(
        manufacturer=manufacturer,
        status="healthy",
        response_time=0.125,
        error_message="",
        details=health_status,
    )
    cache_set.assert_called_once_with("api_health_shure", health_status, timeout=60)
    broadcast.assert_called_once_with(
        manufacturer=manufacturer,
        health_data=health_status,
    )


def test_api_health_check_handles_missing_manufacturer() -> None:
    """A stale queued ID must stop before loading a plugin."""
    with (
        patch.object(
            health_tasks.Manufacturer.objects,
            "get",
            side_effect=health_tasks.Manufacturer.DoesNotExist,
        ),
        patch.object(health_tasks, "get_manufacturer_plugin") as get_plugin,
        patch.object(health_tasks.logger, "warning") as warning,
    ):
        health_tasks.check_manufacturer_api_health(404)

    get_plugin.assert_not_called()
    warning.assert_called_once_with(
        "Manufacturer with ID %s not found for API health check task.",
        404,
    )


def test_api_health_check_contains_plugin_failure() -> None:
    """Integration failures must be logged without escaping the task boundary."""
    manufacturer = Mock(code="shure")
    error = RuntimeError("plugin unavailable")

    with (
        patch.object(
            health_tasks.Manufacturer.objects,
            "get",
            return_value=manufacturer,
        ),
        patch.object(
            health_tasks,
            "get_manufacturer_plugin",
            side_effect=error,
        ),
        patch.object(health_tasks.logger, "exception") as exception,
    ):
        health_tasks.check_manufacturer_api_health(9)

    exception.assert_called_once_with(
        "Error checking API health for manufacturer ID %s: %s",
        9,
        error,
    )


def test_realtime_health_check_disconnects_stale_and_resets_old_errors() -> None:
    """Connection cleanup must apply both stale and expired-error transitions."""
    now = datetime(2026, 7, 13, 15, 0, tzinfo=UTC)
    stale_connection = Mock(
        chassis="Rack A",
        last_message_at=now - timedelta(minutes=30),
    )
    old_error_connection = Mock(chassis="Rack B")

    stale_connections = MagicMock()
    stale_connections.__iter__.return_value = iter([stale_connection])
    stale_connections.count.return_value = 1
    old_error_connections = MagicMock()
    old_error_connections.__iter__.return_value = iter([old_error_connection])
    active_connections = Mock()
    active_connections.count.return_value = 3
    current_errors = Mock()
    current_errors.count.return_value = 1

    with (
        patch.object(health_tasks.timezone, "now", return_value=now),
        patch.object(
            health_tasks.RealTimeConnection.objects,
            "filter",
            side_effect=[
                stale_connections,
                old_error_connections,
                active_connections,
                current_errors,
            ],
        ) as filter_connections,
    ):
        health_tasks.check_realtime_connection_health()

    assert filter_connections.call_args_list == [
        call(status="connected", last_message_at__lt=now - timedelta(minutes=10)),
        call(status="error", last_error_at__lt=now - timedelta(hours=1)),
        call(status="connected"),
        call(status="error"),
    ]
    stale_connection.mark_disconnected.assert_called_once_with(
        "Connection appears stale - no messages received"
    )
    assert old_error_connection.status == "disconnected"
    assert old_error_connection.error_count == 0
    assert old_error_connection.error_message == ""
    old_error_connection.save.assert_called_once_with()


def test_realtime_health_check_contains_query_failure() -> None:
    """Database failures must be logged without escaping the task boundary."""
    error = RuntimeError("database unavailable")

    with (
        patch.object(
            health_tasks.RealTimeConnection.objects,
            "filter",
            side_effect=error,
        ),
        patch.object(health_tasks.logger, "exception") as exception,
    ):
        health_tasks.check_realtime_connection_health()

    exception.assert_called_once_with(
        "Error checking real-time connection health: %s",
        error,
    )


def test_realtime_status_summarizes_counts_and_percentage() -> None:
    """Status output must expose every state and a useful connected percentage."""
    filtered_connections = Mock()
    filtered_connections.count.side_effect = [4, 1, 2, 2, 1]

    with (
        patch.object(
            health_tasks.RealTimeConnection.objects,
            "count",
            return_value=10,
        ),
        patch.object(
            health_tasks.RealTimeConnection.objects,
            "filter",
            return_value=filtered_connections,
        ) as filter_connections,
    ):
        status = health_tasks.get_realtime_connection_status()

    assert status == {
        "total": 10,
        "connected": 4,
        "connecting": 1,
        "disconnected": 2,
        "error": 2,
        "stopped": 1,
        "healthy_percentage": 40.0,
    }
    assert filter_connections.call_args_list == [
        call(status="connected"),
        call(status="connecting"),
        call(status="disconnected"),
        call(status="error"),
        call(status="stopped"),
    ]


def test_realtime_status_returns_error_when_query_fails() -> None:
    """Status callers receive a stable error payload when the database fails."""
    error = RuntimeError("database unavailable")

    with (
        patch.object(
            health_tasks.RealTimeConnection.objects,
            "count",
            side_effect=error,
        ),
        patch.object(health_tasks.logger, "exception") as exception,
    ):
        status = health_tasks.get_realtime_connection_status()

    assert status == {"error": "database unavailable"}
    exception.assert_called_once_with(
        "Error getting real-time connection status: %s",
        error,
    )


def test_charger_poll_maps_supported_devices_and_slots_into_cache() -> None:
    """Supported charger payloads must become the dashboard cache contract."""
    manufacturer = Mock(code="shure")
    plugin = Mock()
    plugin.get_devices.return_value = [
        {"api_device_id": "station-1", "model": "SBC250"},
        {
            "api_device_id": "station-2",
            "model": "Other",
            "device_type": "MXWNCS4",
            "name": "Green Room Charger",
        },
        {"api_device_id": "receiver-1", "model": "AD4Q"},
        {"api_device_id": 99, "model": "SBC850"},
    ]
    plugin.get_device_channels.side_effect = [
        [
            {
                "channel": 2,
                "tx": {
                    "name": "Handheld 2",
                    "battery_percentage": 87,
                    "charging_status": True,
                },
            },
            {"channel": 3, "tx": None},
        ],
        [],
    ]
    client = Mock()
    client.is_healthy.side_effect = [True, False]
    plugin.get_client.return_value = client
    plugin_class = Mock(return_value=plugin)

    with (
        patch.object(
            charger_tasks.Manufacturer.objects,
            "get",
            return_value=manufacturer,
        ),
        patch.object(
            charger_tasks,
            "get_manufacturer_plugin",
            return_value=plugin_class,
        ),
        patch.object(charger_tasks.cache, "set") as cache_set,
    ):
        charger_tasks.poll_charger_data(23)

    assert plugin.get_device_channels.call_args_list == [call("station-1"), call("station-2")]
    cache_set.assert_called_once_with(
        "charger_data_shure",
        [
            {
                "id": "station-1",
                "name": "Charger station-1",
                "status": "online",
                "slots": [
                    {
                        "slot_number": 2,
                        "mic_name": "Handheld 2",
                        "battery_level": 87,
                        "charging": True,
                    }
                ],
            },
            {
                "id": "station-2",
                "name": "Green Room Charger",
                "status": "offline",
                "slots": [],
            },
        ],
        timeout=60,
    )


def test_charger_poll_caches_station_when_channel_read_fails() -> None:
    """One channel API failure must not discard a discovered charging station."""
    manufacturer = Mock(code="shure")
    plugin = Mock()
    plugin.get_devices.return_value = [
        {"api_device_id": "station-3", "device_type": "SBC220", "name": "Wardrobe"}
    ]
    channel_error = RuntimeError("channel endpoint unavailable")
    plugin.get_device_channels.side_effect = channel_error
    plugin.get_client.return_value.is_healthy.return_value = True

    with (
        patch.object(
            charger_tasks.Manufacturer.objects,
            "get",
            return_value=manufacturer,
        ),
        patch.object(
            charger_tasks,
            "get_manufacturer_plugin",
            return_value=Mock(return_value=plugin),
        ),
        patch.object(charger_tasks.cache, "set") as cache_set,
        patch.object(charger_tasks.logger, "warning") as warning,
    ):
        charger_tasks.poll_charger_data(24)

    warning.assert_called_once_with(
        "Could not read charger channels for device %s",
        "station-3",
        exc_info=True,
    )
    cache_set.assert_called_once_with(
        "charger_data_shure",
        [
            {
                "id": "station-3",
                "name": "Wardrobe",
                "status": "online",
                "slots": [],
            }
        ],
        timeout=60,
    )


def test_charger_poll_handles_missing_manufacturer() -> None:
    """A stale queued manufacturer ID must not load any plugin."""
    with (
        patch.object(
            charger_tasks.Manufacturer.objects,
            "get",
            side_effect=charger_tasks.Manufacturer.DoesNotExist,
        ),
        patch.object(charger_tasks, "get_manufacturer_plugin") as get_plugin,
        patch.object(charger_tasks.logger, "warning") as warning,
    ):
        charger_tasks.poll_charger_data(404)

    get_plugin.assert_not_called()
    warning.assert_called_once_with(
        "Manufacturer with ID %s not found for charger polling task.",
        404,
    )


def test_charger_poll_contains_plugin_failure() -> None:
    """Plugin failures must be logged without escaping the task boundary."""
    manufacturer = Mock(code="shure")
    error = RuntimeError("plugin unavailable")

    with (
        patch.object(
            charger_tasks.Manufacturer.objects,
            "get",
            return_value=manufacturer,
        ),
        patch.object(
            charger_tasks,
            "get_manufacturer_plugin",
            side_effect=error,
        ),
        patch.object(charger_tasks.logger, "exception") as exception,
    ):
        charger_tasks.poll_charger_data(25)

    exception.assert_called_once_with(
        "Error polling charger data for manufacturer ID %s: %s",
        25,
        error,
    )
