"""Operator-facing activity and synchronization admin display contracts."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

import pytest

from micboard.admin.activity_logs import ActivityLogAdmin, ServiceSyncLogAdmin
from micboard.models.audit.activity_log import ActivityLog, ServiceSyncLog


def _activity(**overrides: object) -> SimpleNamespace:
    values = {
        "activity_type": "crud",
        "operation": "create",
        "status": "success",
        "service_code": "",
        "user": None,
        "get_activity_type_display": Mock(return_value="CRUD Operation"),
        "get_operation_display": Mock(return_value="Create"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("activity_type", ["crud", "service", "sync", "compliance", "unknown"])
def test_activity_type_badge_renders_display_value(activity_type: str) -> None:
    """Known and future activity types remain readable in the changelist."""
    model_admin = ActivityLogAdmin(ActivityLog, AdminSite())

    rendered = model_admin.activity_type_badge(_activity(activity_type=activity_type))

    assert "CRUD Operation" in rendered
    assert "<span" in rendered


@pytest.mark.parametrize(
    "operation",
    [
        "create",
        "update",
        "delete",
        "read",
        "start",
        "stop",
        "success",
        "failure",
        "warning",
        "unknown",
    ],
)
def test_operation_badge_renders_display_value(operation: str) -> None:
    """Every persisted operation and unknown future values have a badge."""
    model_admin = ActivityLogAdmin(ActivityLog, AdminSite())

    rendered = model_admin.operation_badge(_activity(operation=operation))

    assert "Create" in rendered
    assert "<span" in rendered


def test_activity_actor_display_handles_user_service_and_system() -> None:
    """Actor links degrade to service and system labels without ambiguity."""
    model_admin = ActivityLogAdmin(ActivityLog, AdminSite())
    user = SimpleNamespace(get_username=Mock(return_value="operator"))

    assert model_admin.user_name(_activity(user=user)) == "operator"
    assert model_admin.user_name(_activity(service_code="poller")) == "[poller]"
    assert model_admin.user_name(_activity()) == "System"


def test_activity_actor_link_and_search_follow_the_configured_user_model() -> None:
    """Custom user metadata drives links and search without auth.User assumptions."""

    class CustomUser:
        pk = 4
        _meta = SimpleNamespace(app_label="accounts", model_name="member")

        @staticmethod
        def get_username() -> str:
            return "operator@example.test"

    site = AdminSite()
    model_admin = ActivityLogAdmin(ActivityLog, site)
    user = CustomUser()

    with (
        patch.object(site, "is_registered", return_value=True),
        patch(
            "micboard.admin.activity_logs.reverse",
            return_value="/admin/accounts/member/4/",
        ) as reverse,
    ):
        assert "operator@example.test" in model_admin.user_name(_activity(user=user))
    reverse.assert_called_once_with("admin:accounts_member_change", args=[4])

    with patch(
        "micboard.admin.activity_logs.get_user_model",
        return_value=SimpleNamespace(USERNAME_FIELD="email"),
    ):
        assert model_admin.get_search_fields(RequestFactory().get("/")) == (
            "summary",
            "service_code",
            "user__email",
        )


def test_operational_log_admins_are_view_only() -> None:
    """Interactive admin users cannot forge, rewrite, or delete audit history."""
    request = RequestFactory().get("/")

    for model_admin in (
        ActivityLogAdmin(ActivityLog, AdminSite()),
        ServiceSyncLogAdmin(ServiceSyncLog, AdminSite()),
    ):
        assert model_admin.has_add_permission(request) is False
        assert model_admin.has_change_permission(request) is False
        assert model_admin.has_delete_permission(request) is False


@pytest.mark.parametrize("status", ["success", "failed", "warning", "unknown"])
def test_activity_status_badge_handles_known_and_future_values(status: str) -> None:
    """Status presentation never fails on a newly introduced value."""
    model_admin = ActivityLogAdmin(ActivityLog, AdminSite())

    rendered = model_admin.status_badge(_activity(status=status))

    assert status.upper() in rendered


@pytest.mark.parametrize("sync_type", ["full", "incremental", "health_check", "unknown"])
def test_sync_admin_display_and_duration_branches(sync_type: str) -> None:
    """Synchronization rows cover short, long, known, and future display values."""
    model_admin = ServiceSyncLogAdmin(ServiceSyncLog, AdminSite())
    service = SimpleNamespace(name="Vendor")
    sync = SimpleNamespace(
        service=service,
        sync_type=sync_type,
        status="success",
        get_sync_type_display=Mock(return_value="Full Sync"),
        get_status_display=Mock(return_value="Success"),
        duration_seconds=Mock(return_value=59),
    )

    assert model_admin.service_name(sync) == "Vendor"
    assert "Full Sync" in model_admin.sync_type_badge(sync)
    assert "Success" in model_admin.status_badge(sync)
    assert model_admin.duration(sync) == "59s"
    assert model_admin.duration_display(sync) == "59 seconds"

    sync.duration_seconds.return_value = 125
    assert model_admin.duration(sync) == "2m 5s"


@pytest.mark.parametrize("status", ["partial", "failed", "unknown"])
def test_sync_status_badge_handles_remaining_values(status: str) -> None:
    """Partial, failed, and future synchronization states remain readable."""
    model_admin = ServiceSyncLogAdmin(ServiceSyncLog, AdminSite())
    sync = SimpleNamespace(status=status, get_status_display=Mock(return_value=status.title()))

    assert status.title() in model_admin.status_badge(sync)
