"""Focused behavior tests for maintenance and monitoring task wrappers."""

from __future__ import annotations

from unittest.mock import Mock, patch

from micboard.services.chargers.polling_dtos import ChargerPollResult
from micboard.services.realtime.health_dtos import RealtimeConnectionHealthResult
from micboard.tasks.maintenance import charger as charger_tasks
from micboard.tasks.monitoring import health as health_tasks
from micboard.tasks.monitoring import sse as sse_tasks
from micboard.tasks.monitoring import websocket as websocket_tasks


def test_sse_subscription_task_delegates_only_persisted_ids() -> None:
    """The SSE queue seam passes no vendor-controlled device identifier."""
    with patch.object(sse_tasks, "run_sse_subscriptions") as run:
        sse_tasks.start_sse_subscriptions(7, 17)

    run.assert_called_once_with(7, chassis_id=17)


def test_websocket_subscription_task_delegates_only_persisted_ids() -> None:
    """The WebSocket queue seam passes no vendor-controlled device identifier."""
    with patch.object(websocket_tasks, "run_shure_websocket_subscriptions") as run:
        websocket_tasks.start_shure_websocket_subscriptions(8, 18)

    run.assert_called_once_with(8, chassis_id=18)


def test_realtime_health_task_serializes_bounded_service_result() -> None:
    """The worker boundary delegates cleanup and returns a queue-safe dictionary."""
    result = RealtimeConnectionHealthResult(
        stale_disconnected=2,
        errors_reset=1,
        active=3,
        errors=0,
        stale_truncated=True,
    )
    with patch.object(
        health_tasks.RealtimeConnectionHealthService,
        "cleanup",
        return_value=result,
    ) as cleanup:
        assert health_tasks.check_realtime_connection_health() == result.model_dump()

    cleanup.assert_called_once_with()


def test_realtime_health_check_contains_query_failure() -> None:
    """Database failures retain only their type at the worker boundary."""
    secret = "database-password-in-error"
    error = RuntimeError(secret)

    with (
        patch.object(
            health_tasks.RealtimeConnectionHealthService,
            "cleanup",
            side_effect=error,
        ),
        patch.object(health_tasks.logger, "exception") as exception,
    ):
        result = health_tasks.check_realtime_connection_health()

    assert result["failed"] is True
    assert result["error_type"] == "RuntimeError"
    assert secret not in str(result)
    assert exception.call_args.args == ("Error checking real-time connection health",)
    assert secret not in str(exception.call_args.kwargs["exc_info"][1])


def test_charger_poll_task_delegates_and_serializes_service_result() -> None:
    """The task boundary resolves an ID and returns only the service DTO."""
    manufacturer = Mock(pk=23)
    result = ChargerPollResult(
        scanned_count=2,
        cached_count=1,
        failed_count=0,
        inventory_truncated=True,
    )
    with (
        patch.object(
            charger_tasks.Manufacturer.objects,
            "get",
            return_value=manufacturer,
        ) as get_manufacturer,
        patch(
            "micboard.services.chargers.polling_service.ChargerPollingService.poll",
            return_value=result,
        ) as poll,
    ):
        assert charger_tasks.poll_charger_data(23) == result.model_dump()

    get_manufacturer.assert_called_once_with(pk=23, is_active=True)
    poll.assert_called_once_with(manufacturer)


def test_charger_poll_handles_missing_manufacturer() -> None:
    """A stale queued manufacturer ID must not load any plugin."""
    with (
        patch.object(
            charger_tasks.Manufacturer.objects,
            "get",
            side_effect=charger_tasks.Manufacturer.DoesNotExist,
        ) as get_manufacturer,
        patch.object(charger_tasks.logger, "warning") as warning,
    ):
        assert charger_tasks.poll_charger_data(404) is None

    warning.assert_called_once_with(
        "Active manufacturer with ID %s not found for charger polling task.",
        404,
    )
    get_manufacturer.assert_called_once_with(pk=404, is_active=True)


def test_charger_poll_contains_plugin_failure() -> None:
    """Plugin failures must be logged without escaping the task boundary."""
    manufacturer = Mock(pk=25)
    secret = "plugin-credential-in-error"
    error = RuntimeError(secret)

    with (
        patch.object(
            charger_tasks.Manufacturer.objects,
            "get",
            return_value=manufacturer,
        ),
        patch(
            "micboard.services.chargers.polling_service.ChargerPollingService.poll",
            side_effect=error,
        ),
        patch.object(charger_tasks.logger, "exception") as exception,
    ):
        assert charger_tasks.poll_charger_data(25) is None

    assert exception.call_args.args == (
        "Error polling charger data for manufacturer ID %s",
        25,
    )
    assert secret not in str(exception.call_args.kwargs["exc_info"][1])
