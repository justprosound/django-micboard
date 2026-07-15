"""Behavioral contracts for the admin-audit orchestrator and command."""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.management.color import no_style
from django.test import override_settings

import pytest

from micboard.exceptions import AdminAuditSetupError
from micboard.management.commands import audit_admin as command_module
from micboard.services.maintenance import admin_audit_service as service_module
from micboard.services.maintenance.admin_audit_dtos import (
    MAX_ADMIN_AUDIT_THREADS,
    AdminAuditMessage,
    AdminAuditOptions,
    AdminAuditReport,
    AdminAuditStats,
    AdminModelAuditResult,
)
from micboard.services.maintenance.admin_audit_service import AdminAuditService


def _model(name: str = "Receiver", *, app_label: str = "inventory") -> Any:
    model = type(name, (), {})
    model._meta = SimpleNamespace(app_label=app_label, model_name=name.lower())
    return model


def _model_result(*, issue: bool = False, model_name: str = "Receiver") -> AdminModelAuditResult:
    return AdminModelAuditResult(
        app_label="inventory",
        model_name=model_name,
        messages=(
            AdminAuditMessage(
                text="problem" if issue else "ok",
                severity="warning" if issue else "info",
            ),
        ),
        stats=AdminAuditStats(models_scanned=1, unfold_compliant=1),
    )


def test_service_selects_registry_models_by_app_name_and_exclusion() -> None:
    receiver = _model("Receiver")
    charger = _model("Charger")
    user = _model("User", app_label="accounts")
    registry = {user: Mock(), receiver: Mock(), charger: Mock()}
    service = AdminAuditService()

    selected = service.select_models(
        registry,
        AdminAuditOptions(
            app_label="inventory",
            model_names=("Receiver", "inventory.Charger"),
            excluded_names=("inventory.Charger",),
        ),
    )

    assert selected == [(receiver, registry[receiver])]
    assert service.select_models(registry, AdminAuditOptions(model_names=("accounts.User",))) == [
        (user, registry[user])
    ]


def test_service_handles_empty_registry_before_authentication() -> None:
    report = AdminAuditService().run(AdminAuditOptions(), registry={})

    assert report.matched_models == 0
    assert report.messages[0].text == "No models registered in admin."


def test_service_finds_existing_superuser_and_rejects_missing_account(monkeypatch) -> None:
    manager = MagicMock()
    manager.filter.return_value.first.return_value = None
    monkeypatch.setattr(
        service_module,
        "get_user_model",
        Mock(return_value=SimpleNamespace(_default_manager=manager)),
    )

    with pytest.raises(AdminAuditSetupError, match="existing active superuser"):
        AdminAuditService._find_audit_user()

    expected = object()
    manager.filter.return_value.first.return_value = expected
    assert AdminAuditService._find_audit_user() is expected


def test_service_run_aggregates_results_and_honors_errors_only(monkeypatch) -> None:
    receiver = _model("Receiver")
    charger = _model("Charger")
    service = AdminAuditService()
    monkeypatch.setattr(service, "_authenticated_client", Mock(return_value=Mock()))
    monkeypatch.setattr(
        service, "_check_index", Mock(return_value=[AdminAuditMessage(text="index")])
    )
    monkeypatch.setattr(
        service,
        "_check_unfold_settings",
        Mock(return_value=[AdminAuditMessage(text="settings")]),
    )
    monkeypatch.setattr(
        service,
        "_audit_models",
        Mock(return_value=[_model_result(), _model_result(issue=True, model_name="Charger")]),
    )

    report = service.run(
        AdminAuditOptions(errors_only=True),
        registry={receiver: Mock(), charger: Mock()},
        user=object(),
    )

    assert report.matched_models == 2
    assert report.stats.models_scanned == 2
    assert [message.text for message in report.messages] == [
        "index",
        "settings",
        "--- inventory.Charger ---",
        "problem",
    ]


def test_service_run_reports_no_filter_match(monkeypatch) -> None:
    service = AdminAuditService()
    monkeypatch.setattr(service, "_authenticated_client", Mock(return_value=Mock()))
    report = service.run(
        AdminAuditOptions(model_names=("Unknown",)),
        registry={_model(): Mock()},
        user=object(),
    )

    assert report.messages[-1].text == "No models matched the filter."


@pytest.mark.django_db
def test_service_run_removes_privileged_audit_session(admin_user, monkeypatch) -> None:
    """A completed audit must not leave reusable superuser sessions in storage."""
    service = AdminAuditService()
    monkeypatch.setattr(service, "_audit_models", Mock(return_value=[_model_result()]))
    before = Session.objects.count()

    service.run(
        AdminAuditOptions(model_names=("Receiver",)),
        registry={_model(): Mock()},
        user=admin_user,
    )

    assert Session.objects.count() == before


def test_service_audits_models_inline_and_in_thread_pool(monkeypatch) -> None:
    entries = [(_model("B"), Mock()), (_model("A"), Mock())]
    service = AdminAuditService()
    audit = Mock(side_effect=[_model_result(model_name="B"), _model_result(model_name="A")])
    monkeypatch.setattr(service, "_audit_model_safely", audit)

    inline = service._audit_models(entries, object(), AdminAuditOptions(threads=1))
    audit.side_effect = [_model_result(model_name="B"), _model_result(model_name="A")]
    threaded = service._audit_models(entries, object(), AdminAuditOptions(threads=2))

    assert [result.model_name for result in inline] == ["B", "A"]
    assert [result.model_name for result in threaded] == ["B", "A"]


def test_service_contains_worker_failures_and_closes_connections(monkeypatch) -> None:
    service = AdminAuditService()
    secret = "login-backend-secret"
    monkeypatch.setattr(service, "_authenticated_client", Mock(side_effect=RuntimeError(secret)))
    close_all = Mock()
    reset = Mock()
    monkeypatch.setattr(service_module.connections, "close_all", close_all)
    monkeypatch.setattr(service_module, "reset_queries", reset)

    result = service._audit_model_safely((_model(), Mock()), object(), AdminAuditOptions())

    assert result.has_issues is True
    assert "Worker failed (RuntimeError); details redacted." in result.messages[0].text
    assert secret not in result.messages[0].text
    close_all.assert_called_once()
    reset.assert_called_once()


def test_service_worker_returns_model_audit_result(monkeypatch) -> None:
    service = AdminAuditService()
    expected = _model_result()
    audit_instance = Mock()
    audit_instance.audit.return_value = expected
    audit_class = Mock(return_value=audit_instance)
    monkeypatch.setattr(service, "_authenticated_client", Mock(return_value=Mock()))
    monkeypatch.setattr(service_module, "AdminModelAuditService", audit_class)
    monkeypatch.setattr(service_module.connections, "close_all", Mock())
    monkeypatch.setattr(service_module, "reset_queries", Mock())

    assert (
        service._audit_model_safely((_model(), Mock()), object(), AdminAuditOptions()) is expected
    )
    audit_instance.audit.assert_called_once_with()


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (SimpleNamespace(status_code=500, content=b""), "[FAIL] Admin Index: 500"),
        (SimpleNamespace(status_code=200, content=b"UNFOLD"), "Unfold theme detected"),
        (SimpleNamespace(status_code=200, content=b"plain"), "NOT detected"),
    ],
)
def test_index_check_reports_status_and_theme(monkeypatch, response: object, expected: str) -> None:
    reverse = Mock(return_value="/custom-admin/")
    monkeypatch.setattr(service_module, "reverse", reverse)
    client = SimpleNamespace(get=Mock(return_value=response))
    messages = AdminAuditService._check_index(
        client  # type: ignore[arg-type]
    )
    assert any(expected in message.text for message in messages)
    reverse.assert_called_once_with("admin:index")
    client.get.assert_called_once_with("/custom-admin/")


def test_index_check_contains_request_exception() -> None:
    secret = "admin-session-secret"
    messages = AdminAuditService._check_index(
        SimpleNamespace(get=Mock(side_effect=RuntimeError(secret)))  # type: ignore[arg-type]
    )
    assert messages[0].severity == "error"
    assert messages[0].text == "[ERROR] Admin Index (RuntimeError); details redacted."
    assert secret not in messages[0].text


@override_settings(UNFOLD={"SITE_TITLE": "Micboard"})
def test_settings_check_reports_present_and_missing_configuration() -> None:
    assert AdminAuditService._check_unfold_settings()[0].severity == "info"
    with override_settings(UNFOLD={}):
        assert AdminAuditService._check_unfold_settings()[0].severity == "error"


def test_authenticated_client_wraps_login_failure_and_returns_success(monkeypatch) -> None:
    client = Mock()
    secret = "authentication-backend-secret"
    client.force_login.side_effect = RuntimeError(secret)
    monkeypatch.setattr(service_module, "Client", Mock(return_value=client))
    with pytest.raises(AdminAuditSetupError, match="RuntimeError") as exc_info:
        AdminAuditService._authenticated_client(object())
    assert secret not in str(exc_info.value)

    successful = Mock()
    monkeypatch.setattr(service_module, "Client", Mock(return_value=successful))
    user = object()
    assert AdminAuditService._authenticated_client(user) is successful
    successful.force_login.assert_called_once_with(user)


def _command_options() -> dict[str, object]:
    return {
        "errors_only": True,
        "quick": True,
        "check_n1": False,
        "check_unfold": False,
        "check_media": False,
        "check_search_depth": False,
        "model": None,
        "app": None,
        "exclude": None,
        "threads": 1,
    }


def test_command_parser_preserves_public_flags() -> None:
    options = vars(
        command_module.Command()
        .create_parser("manage.py", "audit_admin")
        .parse_args(
            [
                "--app",
                "inventory",
                "--model",
                "Receiver",
                "--exclude",
                "Charger",
                "--errors-only",
                "--quick",
                "--check-n1",
                "--check-unfold",
                "--check-media",
                "--check-search-depth",
                "--threads",
                "3",
            ]
        )
    )
    assert options["app"] == "inventory"
    assert options["model"] == ["Receiver"]
    assert options["exclude"] == ["Charger"]
    assert options["threads"] == 3

    defaults = vars(
        command_module.Command().create_parser("manage.py", "audit_admin").parse_args([])
    )
    assert 1 <= defaults["threads"] <= MAX_ADMIN_AUDIT_THREADS


@override_settings(DEBUG=True)
def test_command_handle_restores_debug_and_writes_report(monkeypatch) -> None:
    report = AdminAuditReport(
        messages=(AdminAuditMessage(text="warning", severity="warning"),),
        stats=AdminAuditStats(models_scanned=1),
        matched_models=1,
    )
    monkeypatch.setattr(command_module.AdminAuditService, "run", Mock(return_value=report))
    command = command_module.Command()
    command.style = no_style()
    command.stdout = StringIO()  # type: ignore[assignment]

    command.handle(**_command_options())

    assert settings.DEBUG is True
    assert "warning" in command.stdout.getvalue()  # type: ignore[attr-defined]
    assert "AUDIT SUMMARY" in command.stdout.getvalue()  # type: ignore[attr-defined]


@override_settings(DEBUG=True)
def test_command_handle_restores_debug_after_setup_error(monkeypatch) -> None:
    secret = "admin-user-secret"
    monkeypatch.setattr(
        command_module.AdminAuditService,
        "run",
        Mock(side_effect=AdminAuditSetupError(secret)),
    )
    with pytest.raises(CommandError, match="AdminAuditSetupError") as exc_info:
        command_module.Command().handle(**_command_options())
    assert secret not in str(exc_info.value)
    assert settings.DEBUG is True


def test_command_rejects_invalid_thread_count() -> None:
    with pytest.raises(CommandError, match="Invalid admin audit options"):
        command_module.Command._build_options({"threads": 0})


@override_settings(DEBUG=False)
def test_command_default_output_includes_header_without_empty_summary(monkeypatch) -> None:
    report = AdminAuditReport(messages=(AdminAuditMessage(text="No models"),))
    monkeypatch.setattr(command_module.AdminAuditService, "run", Mock(return_value=report))
    command = command_module.Command()
    command.stdout = StringIO()  # type: ignore[assignment]
    options = _command_options()
    options["errors_only"] = False

    command.handle(**options)

    output = command.stdout.getvalue()  # type: ignore[attr-defined]
    assert "Starting Micboard Admin Audit" in output
    assert "No models" in output
    assert "AUDIT SUMMARY" not in output


@pytest.mark.django_db
def test_command_runs_filtered_static_audit_against_live_registry(admin_user) -> None:
    output = StringIO()

    call_command(
        "audit_admin",
        "--model",
        "ManufacturerAPIServer",
        "--check-media",
        "--quick",
        "--threads",
        "1",
        stdout=output,
        no_color=True,
    )

    assert "micboard.ManufacturerAPIServer" in output.getvalue()
    assert "Total Models Scanned:   1" in output.getvalue()


@pytest.mark.django_db
@override_settings(ALLOWED_HOSTS=["example.test"])
def test_command_audits_index_without_persisting_host_override(admin_user) -> None:
    output = StringIO()

    call_command(
        "audit_admin",
        "--app",
        "not-installed",
        "--quick",
        "--threads",
        "1",
        stdout=output,
        no_color=True,
    )

    assert "[PASS] Admin Index" in output.getvalue()
    assert settings.ALLOWED_HOSTS == ["example.test"]
