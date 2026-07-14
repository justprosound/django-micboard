"""Behavioral coverage for structured maintenance logging."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from micboard.models.audit.activity_log import ActivityLog
from micboard.services.maintenance import logging as logging_module
from micboard.services.maintenance.logging import StructuredLogger, get_structured_logger


class _Device:
    pk = 7

    def __str__(self) -> str:
        return "Device seven"


@pytest.mark.parametrize(
    ("method_name", "operation"),
    [
        ("log_crud_create", ActivityLog.CREATE),
        ("log_crud_delete", ActivityLog.DELETE),
    ],
)
def test_structured_crud_logging_preserves_caller_extra(
    monkeypatch, method_name: str, operation: str
) -> None:
    log = object()
    log_crud = Mock(return_value=log)
    monkeypatch.setattr(logging_module.ActivityLog, "log_crud", log_crud)
    extra = {"request_id": "abc"}
    method = getattr(StructuredLogger, method_name)
    kwargs = (
        {"new_values": {"name": "new"}}
        if operation == ActivityLog.CREATE
        else {"old_values": {"name": "old"}}
    )

    assert method(_Device(), extra=extra, using="replica", **kwargs) is log
    assert extra == {"request_id": "abc"}
    assert log_crud.call_args.kwargs["operation"] == operation
    assert log_crud.call_args.kwargs["using"] == "replica"


def test_structured_update_logging_reports_changed_keys_without_mutating_extra(monkeypatch) -> None:
    log = object()
    monkeypatch.setattr(logging_module.ActivityLog, "log_crud", Mock(return_value=log))
    logger_info = Mock()
    monkeypatch.setattr(logging_module.logger, "info", logger_info)
    extra = {"request_id": "abc"}

    assert (
        StructuredLogger.log_crud_update(
            _Device(),
            old_values={"same": 1},
            new_values={"same": 2, "new": 3},
            extra=extra,
        )
        is log
    )
    assert extra == {"request_id": "abc"}
    assert logger_info.call_args.kwargs["extra"]["changes"] == {"new"}


@pytest.mark.parametrize(
    ("method_name", "operation", "status"),
    [
        ("log_service_start", ActivityLog.START, "success"),
        ("log_service_stop", ActivityLog.STOP, "success"),
    ],
)
def test_structured_service_lifecycle_logging(
    monkeypatch, method_name: str, operation: str, status: str
) -> None:
    log = object()
    log_service = Mock(return_value=log)
    monkeypatch.setattr(logging_module.ActivityLog, "log_service", log_service)
    extra = {"trace": 1}

    assert getattr(StructuredLogger, method_name)("shure", extra=extra) is log
    assert extra == {"trace": 1}
    assert log_service.call_args.kwargs["operation"] == operation
    assert log_service.call_args.kwargs["status"] == status


def test_structured_service_error_redacts_exception_without_mutating_extra(monkeypatch) -> None:
    log = object()
    log_service = Mock(return_value=log)
    monkeypatch.setattr(logging_module.ActivityLog, "log_service", log_service)
    extra = {"trace": 1}
    secret = "service-password-in-error"
    error = RuntimeError(secret)

    assert StructuredLogger.log_service_error("shure", error, extra=extra) is log
    assert extra == {"trace": 1}
    assert log_service.call_args.kwargs["error_message"] == (
        "RuntimeError: service error details redacted"
    )
    assert secret not in str(log_service.call_args)


def test_structured_sync_start_handles_missing_and_existing_manufacturer(monkeypatch) -> None:
    query = MagicMock()
    manager = MagicMock()
    manager.filter.return_value = query
    monkeypatch.setattr("micboard.models.discovery.manufacturer.Manufacturer.objects", manager)
    query.first.return_value = None
    assert StructuredLogger.log_sync_start("missing") is None

    manufacturer = SimpleNamespace(code="shure")
    query.first.return_value = manufacturer
    sync_log = object()
    create = Mock(return_value=sync_log)
    monkeypatch.setattr(logging_module.ServiceSyncLog.objects, "create", create)
    extra = {"trace": 1}
    assert StructuredLogger.log_sync_start("shure", "partial", extra=extra) is sync_log
    assert create.call_args.kwargs["service"] is manufacturer
    assert create.call_args.kwargs["sync_type"] == "partial"
    assert extra == {"trace": 1}


@pytest.mark.parametrize(
    ("error_message", "expected_status", "expected_level"),
    [
        ("", "success", logging_module.logging.INFO),
        ("offline", "failed", logging_module.logging.ERROR),
    ],
)
def test_structured_sync_complete_updates_and_logs(
    monkeypatch, error_message: str, expected_status: str, expected_level: int
) -> None:
    sync_log = SimpleNamespace(
        service=SimpleNamespace(code="shure"),
        sync_type="full",
        save=Mock(),
        duration_seconds=Mock(return_value=1.5),
        get_sync_type_display=Mock(return_value="Full"),
    )
    logger_log = Mock()
    monkeypatch.setattr(logging_module.logger, "log", logger_log)
    extra = {"trace": 1}

    result = StructuredLogger.log_sync_complete(
        sync_log,  # type: ignore[arg-type]
        device_count=4,
        online_count=3,
        offline_count=1,
        updated_count=2,
        error_message=error_message,
        extra=extra,
    )

    assert result is sync_log
    assert sync_log.status == expected_status
    assert sync_log.error_message == error_message
    sync_log.save.assert_called_once_with()
    assert logger_log.call_args.args[0] == expected_level
    assert extra == {"trace": 1}
    assert isinstance(get_structured_logger(), StructuredLogger)
