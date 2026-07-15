"""Behavior and failure-path coverage for the maintenance audit service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from django.utils import timezone

import pytest

from micboard.models.audit.activity_log import ActivityLog
from micboard.services.maintenance import audit as audit_module
from micboard.services.maintenance.audit import AuditService


def test_audit_log_activity_respects_mode_and_populates_object_request(monkeypatch) -> None:
    should_log = Mock(side_effect=[False, True])
    monkeypatch.setattr(audit_module.LoggingModeService, "should_log", should_log)
    using_manager = MagicMock()
    created = object()
    using_manager.create.return_value = created
    monkeypatch.setattr(audit_module.ActivityLog.objects, "using", Mock(return_value=using_manager))

    assert (
        AuditService.log_activity(
            activity_type="crud",
            operation="create",
            summary="ignored",
            log_mode="high",
        )
        is None
    )

    content_type = object()
    db_manager = MagicMock()
    db_manager.get_for_model.return_value = content_type
    monkeypatch.setattr(
        "django.contrib.contenttypes.models.ContentType.objects.db_manager",
        Mock(return_value=db_manager),
    )
    instance = SimpleNamespace(pk=17)
    request = SimpleNamespace(META={"REMOTE_ADDR": "192.0.2.9", "HTTP_USER_AGENT": "agent"})
    result = AuditService.log_activity(
        actor="operator",
        activity_type="crud",
        operation="update",
        summary="changed",
        obj=instance,  # type: ignore[arg-type]
        details={"api_key": "private", "safe": 1},
        old_values={"password": "before"},
        new_values={
            "access_token": "after",
            "changed_at": datetime(2026, 7, 14, 12, 30, tzinfo=UTC),
        },
        request=request,  # type: ignore[arg-type]
        using="replica",
    )

    assert result is created
    db_manager.get_for_model.assert_called_once_with(instance)
    using_manager.create.assert_called_once()
    kwargs = using_manager.create.call_args.kwargs
    assert kwargs["content_type"] is content_type
    assert kwargs["object_id"] == 17
    assert kwargs["ip_address"] == "192.0.2.9"
    assert kwargs["user_agent"] == "agent"
    assert kwargs["details"] == {"api_key": "********", "safe": 1}
    assert kwargs["old_values"] == {"password": "********"}
    assert kwargs["new_values"] == {
        "access_token": "********",
        "changed_at": "2026-07-14T12:30:00Z",
    }


@pytest.mark.django_db
def test_audit_archive_handles_empty_and_json_rows(tmp_path: Path) -> None:
    empty_result = AuditService.archive_activity_logs(retention_days=0, path=str(tmp_path))
    assert empty_result["archived"] == 0
    assert Path(str(empty_result["file"])).read_text(encoding="utf-8").startswith("id,")

    activity = ActivityLog.objects.create(
        activity_type=ActivityLog.ACTIVITY_CRUD,
        operation=ActivityLog.CREATE,
        summary="archive JSON",
        details={"value": "2026-01-01T00:00:00"},
        old_values={"before": 1},
        new_values={"after": 2},
    )
    ActivityLog.objects.filter(pk=activity.pk).update(created_at=timezone.now() - timedelta(days=2))
    result = AuditService.archive_activity_logs(retention_days=1, path=str(tmp_path))
    contents = Path(str(result["file"])).read_text(encoding="utf-8")
    assert result["archived"] == 1
    assert "archive JSON" in contents
    assert "2026-01-01T00:00:00" in contents


def test_audit_individual_pruners_and_retention_validation(monkeypatch) -> None:
    monkeypatch.setattr(
        "micboard.services.settings.settings_service.settings",
        SimpleNamespace(
            service_sync_log_retention_days=20,
            api_health_log_retention_days=30,
        ),
    )
    sync_query = MagicMock()
    sync_query.delete.return_value = (4, {})
    health_query = MagicMock()
    health_query.delete.return_value = (5, {})
    monkeypatch.setattr(
        audit_module.ServiceSyncLog.objects, "filter", Mock(return_value=sync_query)
    )
    monkeypatch.setattr(
        audit_module.APIHealthLog.objects, "filter", Mock(return_value=health_query)
    )

    assert AuditService.prune_service_sync_logs() == 4
    assert AuditService.prune_api_health_logs(retention_days=7) == 5
    assert AuditService._resolve_retention_days(None, default=3) == 3
    assert AuditService._resolve_retention_days(0, default=3) == 0
    with pytest.raises(ValueError, match="zero or greater"):
        AuditService._resolve_retention_days(-1, default=3)
