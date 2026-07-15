"""Secret-safe publication contracts for manufacturer API-health tasks."""

from __future__ import annotations

from unittest.mock import Mock, patch

from micboard.services.shared.api_health import API_HEALTH_AGGREGATE_CACHE_KEY
from micboard.services.shared.api_health_dtos import PUBLIC_API_HEALTH_ERROR
from micboard.tasks.monitoring import health as health_tasks

SECRET_SENTINEL = "task-health-secret-sentinel"


def _publisher_patches():
    return (
        patch.object(health_tasks.APIHealthLog.objects, "create"),
        patch.object(health_tasks.cache, "set"),
        patch.object(health_tasks.cache, "delete"),
        patch.object(health_tasks.logger, "info"),
        patch.object(health_tasks.BroadcastService, "broadcast_api_health"),
    )


def test_api_health_check_sanitizes_every_published_snapshot() -> None:
    """Plugin secrets must not reach persistence, cache, logs, or broadcasts."""
    manufacturer = Mock(code="shure")
    raw_health = {
        "status": "unhealthy",
        "response_time": 0.125,
        "error": f"request failed with token={SECRET_SENTINEL}",
        "api_key": SECRET_SENTINEL,
        "firmware": SECRET_SENTINEL,
    }
    client = Mock()
    client.check_health.return_value = raw_health
    plugin = Mock()
    plugin.get_client.return_value = client
    plugin_class = Mock(return_value=plugin)
    safe_health = {
        "status": "unhealthy",
        "response_time": 0.125,
        "error": PUBLIC_API_HEALTH_ERROR,
    }

    create_patch, set_patch, delete_patch, info_patch, broadcast_patch = _publisher_patches()
    with (
        patch.object(health_tasks.Manufacturer.objects, "get", return_value=manufacturer),
        patch.object(health_tasks, "get_manufacturer_plugin", return_value=plugin_class),
        create_patch as create_log,
        set_patch as cache_set,
        delete_patch as cache_delete,
        info_patch as info,
        broadcast_patch as broadcast,
    ):
        health_tasks.check_manufacturer_api_health(17)

    create_log.assert_called_once_with(
        manufacturer=manufacturer,
        status="unhealthy",
        response_time=0.125,
        error_message=PUBLIC_API_HEALTH_ERROR,
        details=safe_health,
    )
    cache_set.assert_called_once_with("api_health_shure", safe_health, timeout=60)
    cache_delete.assert_called_once_with(API_HEALTH_AGGREGATE_CACHE_KEY)
    info.assert_called_once_with("API health for %s: %s", "shure", safe_health)
    broadcast.assert_called_once_with(manufacturer=manufacturer, health_data=safe_health)
    assert SECRET_SENTINEL not in str(
        (create_log.call_args, cache_set.call_args, info.call_args, broadcast.call_args)
    )


def test_api_health_check_handles_missing_manufacturer() -> None:
    """A stale queued ID must stop before loading a plugin."""
    with (
        patch.object(
            health_tasks.Manufacturer.objects,
            "get",
            side_effect=health_tasks.Manufacturer.DoesNotExist,
        ) as get_manufacturer,
        patch.object(health_tasks, "get_manufacturer_plugin") as get_plugin,
        patch.object(health_tasks.logger, "warning") as warning,
    ):
        health_tasks.check_manufacturer_api_health(404)

    get_plugin.assert_not_called()
    warning.assert_called_once_with(
        "Manufacturer with ID %s not found or inactive for API health check task.",
        404,
    )
    get_manufacturer.assert_called_once_with(pk=404, is_active=True)


def test_api_health_check_contains_manufacturer_lookup_failure() -> None:
    """A database failure fails closed before plugin or vendor access."""
    error = RuntimeError(f"database unavailable: {SECRET_SENTINEL}")
    with (
        patch.object(health_tasks.Manufacturer.objects, "get", side_effect=error),
        patch.object(health_tasks, "get_manufacturer_plugin") as get_plugin,
        patch.object(health_tasks.logger, "exception") as exception,
    ):
        health_tasks.check_manufacturer_api_health(404)

    get_plugin.assert_not_called()
    assert str(exception.call_args.kwargs["exc_info"][1]) == (
        "RuntimeError: error details redacted"
    )
    assert SECRET_SENTINEL not in str(exception.call_args)


def test_api_health_check_persists_stable_snapshot_after_plugin_failure() -> None:
    """Probe failures publish an error state without rendering exception text."""
    manufacturer = Mock(code="shure")
    error = RuntimeError(f"plugin unavailable: {SECRET_SENTINEL}")
    safe_health = {"status": "error", "error": PUBLIC_API_HEALTH_ERROR}

    create_patch, set_patch, delete_patch, info_patch, broadcast_patch = _publisher_patches()
    with (
        patch.object(health_tasks.Manufacturer.objects, "get", return_value=manufacturer),
        patch.object(health_tasks, "get_manufacturer_plugin", side_effect=error),
        patch.object(health_tasks.logger, "exception") as exception,
        create_patch as create_log,
        set_patch as cache_set,
        delete_patch,
        info_patch,
        broadcast_patch as broadcast,
    ):
        health_tasks.check_manufacturer_api_health(9)

    create_log.assert_called_once_with(
        manufacturer=manufacturer,
        status="error",
        response_time=None,
        error_message=PUBLIC_API_HEALTH_ERROR,
        details=safe_health,
    )
    cache_set.assert_called_once_with("api_health_shure", safe_health, timeout=60)
    broadcast.assert_called_once_with(manufacturer=manufacturer, health_data=safe_health)
    exception_args = exception.call_args
    assert exception_args.args == ("Error checking API health for manufacturer ID %s", 9)
    assert str(exception_args.kwargs["exc_info"][1]) == "RuntimeError: error details redacted"
    assert SECRET_SENTINEL not in str(exception_args)


def test_api_health_publication_failure_logs_sanitized_exception() -> None:
    """Downstream publication errors stay contained and credential-safe."""
    manufacturer = Mock(code="shure")
    client = Mock()
    client.check_health.return_value = {"status": "healthy"}
    plugin = Mock()
    plugin.get_client.return_value = client
    plugin_class = Mock(return_value=plugin)
    error = RuntimeError(f"database password={SECRET_SENTINEL}")

    with (
        patch.object(health_tasks.Manufacturer.objects, "get", return_value=manufacturer),
        patch.object(health_tasks, "get_manufacturer_plugin", return_value=plugin_class),
        patch.object(health_tasks.APIHealthLog.objects, "create", side_effect=error),
        patch.object(health_tasks.logger, "exception") as exception,
    ):
        health_tasks.check_manufacturer_api_health(11)

    exception_args = exception.call_args
    assert exception_args.args == ("Error publishing API health for manufacturer ID %s", 11)
    assert str(exception_args.kwargs["exc_info"][1]) == "RuntimeError: error details redacted"
    assert SECRET_SENTINEL not in str(exception_args)
