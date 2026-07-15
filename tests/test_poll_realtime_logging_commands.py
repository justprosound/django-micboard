"""Behavioral coverage for polling, real-time, and logging-mode commands."""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call

from django.core.management.base import CommandError

import pytest

from micboard.management.commands import poll_devices as poll_command
from micboard.management.commands import realtime_status as realtime_command
from micboard.management.commands import set_logging_mode as logging_command
from micboard.services.realtime.health_dtos import RealtimeConnectionStatusSummary


class _Query(list):
    def count(self):
        return len(self)

    def select_related(self, *_fields):
        return self

    def exists(self):
        return bool(self)

    def filter(self, **_filters):
        return self

    def order_by(self, *_fields):
        return self


def test_poll_get_manufacturers_and_missing_code(monkeypatch) -> None:
    manufacturer = object()
    get_manufacturer = Mock(return_value=manufacturer)
    monkeypatch.setattr(poll_command.Manufacturer.objects, "get", get_manufacturer)
    assert poll_command.Command._get_manufacturers("shure", force=False) == [manufacturer]
    get_manufacturer.assert_called_once_with(code="shure", is_active=True)
    assert poll_command.Command._get_manufacturers("shure", force=True) == [manufacturer]
    assert get_manufacturer.call_args == call(code="shure")
    poll_command.Manufacturer.objects.get.side_effect = poll_command.Manufacturer.DoesNotExist
    with pytest.raises(CommandError, match="not found"):
        poll_command.Command._get_manufacturers("missing", force=False)

    monkeypatch.setattr(poll_command.Manufacturer.objects, "all", Mock(return_value=[manufacturer]))
    monkeypatch.setattr(poll_command.Manufacturer.objects, "filter", Mock(return_value=[]))
    assert poll_command.Command._get_manufacturers(None, force=True) == [manufacturer]
    assert poll_command.Command._get_manufacturers(None, force=False) == []


def test_poll_handle_sync_async_and_errors(monkeypatch) -> None:
    manufacturer = SimpleNamespace(name="Shure", code="shure", pk=1)
    output = StringIO()
    errors = StringIO()
    command = poll_command.Command(stdout=output, stderr=errors)
    command._get_manufacturers = Mock(return_value=[])
    command.handle(manufacturer=None, **{"async": False}, force=False)
    assert "No manufacturers found" in output.getvalue()

    command._get_manufacturers.return_value = [manufacturer]
    command._poll_manufacturer = Mock()
    command._enqueue_manufacturer = Mock()
    command.handle(manufacturer=None, **{"async": False}, force=False)
    command._poll_manufacturer.assert_called_once()
    command.handle(manufacturer=None, **{"async": True}, force=False)
    command._enqueue_manufacturer.assert_called_once_with(manufacturer, force=False)

    command._get_manufacturers.side_effect = CommandError("bad manufacturer")
    command.handle(manufacturer=None, **{"async": False}, force=False)
    assert "bad manufacturer" in errors.getvalue()
    command._get_manufacturers.side_effect = RuntimeError("database down")
    command.handle(manufacturer=None, **{"async": False}, force=False)
    assert "unexpected error" in errors.getvalue().lower()


def test_poll_enqueue_and_sync_result_paths(monkeypatch) -> None:
    manufacturer = SimpleNamespace(name="Shure", code="shure", pk=1)
    output = StringIO()
    errors = StringIO()
    command = poll_command.Command(stdout=output, stderr=errors)
    monkeypatch.setattr("micboard.utils.dependencies.huey_is_configured", Mock(return_value=False))
    command._enqueue_manufacturer(manufacturer)
    assert "unavailable or unconfigured" in errors.getvalue()

    enqueue = Mock()
    monkeypatch.setattr("micboard.utils.dependencies.huey_is_configured", Mock(return_value=True))
    monkeypatch.setattr("micboard.utils.dependencies.enqueue_huey_task", enqueue)
    command._enqueue_manufacturer(manufacturer)
    assert enqueue.call_args.args[1] == 1
    assert enqueue.call_args.kwargs == {"force": False}

    command._enqueue_manufacturer(manufacturer, force=True)
    assert enqueue.call_args.kwargs == {"force": True}

    queue_secret = "queue-password-in-error"
    enqueue.side_effect = RuntimeError(queue_secret)
    command._enqueue_manufacturer(manufacturer)
    assert "Failed to enqueue async task (RuntimeError); details redacted." in errors.getvalue()
    assert queue_secret not in errors.getvalue()

    service = Mock()
    service.poll_manufacturer.return_value = {
        "devices_created": 1,
        "devices_updated": 2,
        "units_synced": 3,
    }
    command._poll_manufacturer(service, manufacturer)
    assert "1 created, 2 updated, 3 wireless units" in output.getvalue()
    service.poll_manufacturer.assert_called_once_with(manufacturer, force=False)
    api_secret = "vendor-api-token-in-error"
    service.poll_manufacturer.side_effect = RuntimeError(api_secret)
    command._poll_manufacturer(service, manufacturer, force=True)
    assert service.poll_manufacturer.call_args.kwargs == {"force": True}
    assert "Error polling Shure (RuntimeError); details redacted." in errors.getvalue()
    assert api_secret not in errors.getvalue()


def _summary(**overrides):
    result = {
        "total": 2,
        "connected": 1,
        "connecting": 0,
        "disconnected": 1,
        "error": 0,
        "stopped": 0,
        "healthy_percentage": 50.0,
    }
    result.update(overrides)
    return RealtimeConnectionStatusSummary(**result)


def test_realtime_command_error_empty_and_verbose_paths(monkeypatch) -> None:
    output = StringIO()
    errors = StringIO()
    command = realtime_command.Command(stdout=output, stderr=errors)
    secret = "database-password-in-error"
    monkeypatch.setattr(
        realtime_command.RealtimeConnectionHealthService,
        "summarize",
        Mock(
            return_value=RealtimeConnectionStatusSummary(
                failed=True,
                error_type="RuntimeError",
            )
        ),
    )
    command.handle(manufacturer=None, status=None, verbose=False)
    assert "Error getting status (RuntimeError); details redacted." in errors.getvalue()
    assert secret not in errors.getvalue()

    monkeypatch.setattr(
        realtime_command.RealtimeConnectionHealthService,
        "summarize",
        Mock(return_value=_summary()),
    )
    command._get_connections = Mock(return_value=_Query())
    command.handle(manufacturer=None, status=None, verbose=False)
    assert "No connections found" in output.getvalue()

    connection = SimpleNamespace(
        status="error",
        chassis=SimpleNamespace(
            name="Rack",
            manufacturer=SimpleNamespace(name="Vendor"),
        ),
        connected_at="now",
        last_message_at="later",
        error_message=secret,
    )
    command._get_connections.return_value = _Query([connection])
    monkeypatch.setattr(realtime_command, "connection_duration", Mock(return_value="1m"))
    command.handle(manufacturer="vendor", status="error", verbose=True)
    assert "Vendor - Rack: ERROR" in output.getvalue()
    assert "Error: present; details redacted" in output.getvalue()
    assert secret not in output.getvalue()
    assert "Duration: 1m" in output.getvalue()


def test_realtime_queryset_filters_and_status_styles(monkeypatch) -> None:
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    monkeypatch.setattr(
        realtime_command.RealTimeConnection.objects,
        "select_related",
        Mock(return_value=query),
    )
    assert realtime_command.Command._get_connections("shure", "connected") is query
    assert query.filter.call_args_list == [
        call(chassis__manufacturer__code="shure"),
        call(status="connected"),
    ]
    command = realtime_command.Command()
    for status in ("connected", "connecting", "disconnected", "error", "stopped"):
        assert command._style_status(status).strip() == status.upper()


@pytest.mark.parametrize(("duration", "ttl"), [(None, None), (5, 300)])
def test_set_logging_command_converts_minutes(monkeypatch, duration, ttl) -> None:
    set_mode = Mock()
    monkeypatch.setattr(logging_command.LoggingModeService, "set_mode", set_mode)
    output = StringIO()
    command = logging_command.Command(stdout=output)
    command.handle(mode="high", duration=duration)
    set_mode.assert_called_once_with("high", ttl_seconds=ttl)
    assert ("Duration" in output.getvalue()) is (duration is not None)
