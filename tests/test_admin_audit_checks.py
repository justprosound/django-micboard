"""Behavioral contracts for admin-audit DTOs and model-level checks."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from micboard.services.maintenance import admin_audit_checks as checks_module
from micboard.services.maintenance.admin_audit_checks import AdminModelAuditService
from micboard.services.maintenance.admin_audit_dtos import (
    MAX_ADMIN_AUDIT_THREADS,
    AdminAuditMessage,
    AdminAuditOptions,
    AdminAuditStats,
    AdminModelAuditResult,
)


def _model(name: str = "Receiver", *, app_label: str = "inventory") -> Any:
    model = type(name, (), {})
    model._meta = SimpleNamespace(
        app_label=app_label,
        model_name=name.lower(),
        get_field=Mock(),
    )
    return model


def _model_result(*, issue: bool = False) -> AdminModelAuditResult:
    return AdminModelAuditResult(
        app_label="inventory",
        model_name="Receiver",
        messages=(
            AdminAuditMessage(
                text="problem" if issue else "ok",
                severity="warning" if issue else "info",
            ),
        ),
        stats=AdminAuditStats(models_scanned=1),
    )


def _checker(
    *,
    model: Any | None = None,
    model_admin: Any | None = None,
    options: AdminAuditOptions | None = None,
    client: Any | None = None,
) -> AdminModelAuditService:
    return AdminModelAuditService(
        model=model or _model(),
        model_admin=model_admin or SimpleNamespace(),
        client=client or Mock(),
        options=options or AdminAuditOptions(quick=True),
    )


def test_admin_audit_dtos_normalize_filters_and_derive_issue_state() -> None:
    options = AdminAuditOptions(
        model_names="Receiver",
        excluded_names=["inventory.Charger"],
        check_media=True,
    )

    assert options.model_names == ("Receiver",)
    assert options.excluded_names == ("inventory.Charger",)
    assert options.has_check_filter is True
    assert AdminAuditOptions(model_names=None, excluded_names=None).model_names == ()
    assert AdminAuditOptions().has_check_filter is False
    assert _model_result(issue=True).has_issues is True
    assert _model_result().has_issues is False
    assert AdminAuditStats.from_mapping({"models_scanned": 3}).models_scanned == 3
    with pytest.raises(ValidationError):
        AdminAuditOptions(threads=0)
    with pytest.raises(ValidationError):
        AdminAuditOptions(threads=MAX_ADMIN_AUDIT_THREADS + 1)
    with pytest.raises(ValidationError, match="collections of strings"):
        AdminAuditOptions(model_names=object())


def test_default_model_audit_runs_each_category_and_quick_skips_live_capture(monkeypatch) -> None:
    checker = _checker()
    methods = [
        "_check_unfold_inheritance",
        "_check_unfold_widgets",
        "_check_unfold_filters",
        "_check_deprecated_media_class",
        "_check_search_depth",
        "_check_custom_templates",
        "_check_static_query_optimization",
    ]
    spies = {name: Mock() for name in methods}
    for name, spy in spies.items():
        monkeypatch.setattr(checker, name, spy)
    runtime = Mock()
    monkeypatch.setattr(checker, "_check_runtime_query_count", runtime)

    result = checker.audit()

    assert result.stats.models_scanned == 1
    assert result.messages[-1].text.endswith("skipped in quick mode")
    assert all(spy.call_count == 1 for spy in spies.values())
    runtime.assert_not_called()


@pytest.mark.parametrize(
    ("option", "expected", "unexpected"),
    [
        ("check_unfold", "_check_unfold_inheritance", "_check_deprecated_media_class"),
        ("check_media", "_check_deprecated_media_class", "_check_search_depth"),
        ("check_search_depth", "_check_search_depth", "_check_unfold_inheritance"),
        ("check_n1", "_check_runtime_query_count", "_check_custom_templates"),
    ],
)
def test_selected_model_audit_runs_only_requested_category(
    monkeypatch,
    option: str,
    expected: str,
    unexpected: str,
) -> None:
    checker = _checker(options=AdminAuditOptions(**{option: True}))
    expected_spy = Mock()
    unexpected_spy = Mock()
    monkeypatch.setattr(checker, expected, expected_spy)
    monkeypatch.setattr(checker, unexpected, unexpected_spy)

    checker.audit()

    expected_spy.assert_called_once()
    unexpected_spy.assert_not_called()


def test_unfold_checks_report_inheritance_widgets_and_filters(monkeypatch) -> None:
    class UnfoldAdmin:
        formfield_overrides = {
            object: {"widget": type("Widget", (), {"__module__": "unfold.widgets.text"})}
        }
        list_filter = (type("Filter", (), {"__module__": "unfold.contrib.filters.text"}),)

    monkeypatch.setattr("unfold.admin.ModelAdmin", UnfoldAdmin)
    checker = _checker(model_admin=UnfoldAdmin())

    checker._check_unfold_inheritance()
    checker._check_unfold_widgets()
    checker._check_unfold_filters()

    assert checker._stats["unfold_compliant"] == 1
    assert checker._stats["widgets_optimized"] == 1
    assert checker._stats["filters_optimized"] == 1


def test_unfold_checks_warn_for_plain_admin_and_ignore_other_widgets(monkeypatch) -> None:
    class UnfoldAdmin:
        pass

    monkeypatch.setattr("unfold.admin.ModelAdmin", UnfoldAdmin)
    checker = _checker(model_admin=SimpleNamespace(formfield_overrides={}, list_filter=()))
    checker._check_unfold_inheritance()
    assert checker._stats["unfold_non_compliant"] == 1
    assert checker._messages[0].severity == "warning"

    unoptimized = _checker(
        model_admin=SimpleNamespace(
            formfield_overrides={object: {"widget": None}, str: {"widget": str}},
            list_filter=("name",),
        )
    )
    unoptimized._check_unfold_widgets()
    unoptimized._check_unfold_filters()
    assert unoptimized._messages == []


def test_media_and_search_checks_emit_actionable_findings() -> None:
    class LegacyAdmin:
        class Media:
            js = ("legacy.js",)

        search_fields = ("name", "organization__name")

    checker = _checker(model_admin=LegacyAdmin())
    checker._check_deprecated_media_class()
    checker._check_search_depth()
    assert checker._stats["media_warnings"] == 1
    assert checker._stats["search_warnings"] == 1

    clean = _checker(model_admin=SimpleNamespace(search_fields=("name",)))
    clean._check_deprecated_media_class()
    clean._check_search_depth()
    assert clean._messages == [
        AdminAuditMessage(text="  [SRCH] Search fields use local columns only")
    ]

    empty = _checker(model_admin=SimpleNamespace(search_fields=()))
    empty._check_search_depth()
    assert empty._messages == []


def test_static_query_check_warns_only_for_unoptimized_relations() -> None:
    from django.core.exceptions import FieldDoesNotExist

    model = _model()
    relational = SimpleNamespace(is_relation=True, many_to_one=True, one_to_one=False)
    scalar = SimpleNamespace(is_relation=False, many_to_one=False, one_to_one=False)
    model._meta.get_field.side_effect = [relational, scalar, FieldDoesNotExist]
    checker = _checker(
        model=model,
        model_admin=SimpleNamespace(
            list_display=("manufacturer", "name", "computed", object()),
            list_select_related=False,
            list_prefetch_related=(),
        ),
    )
    checker._check_static_query_optimization()
    assert "manufacturer" in checker._messages[0].text

    model._meta.get_field.side_effect = [relational]
    optimized = _checker(
        model=model,
        model_admin=SimpleNamespace(
            list_display=("manufacturer",),
            list_select_related=("manufacturer",),
        ),
    )
    optimized._check_static_query_optimization()
    assert optimized._messages == []


def test_template_helpers_accept_fallbacks_and_known_sortable_overrides() -> None:
    assert AdminModelAuditService._is_sortable_template(
        ("adminsortable2/change_list.html", "admin/change_list.html"), True, True
    )
    assert not AdminModelAuditService._is_sortable_template("custom.html", True, True)
    assert not AdminModelAuditService._is_sortable_template("adminsortable2/a.html", False, True)

    missing = type("Missing", (Exception,), {})
    loader = Mock(side_effect=[missing(), object()])
    assert AdminModelAuditService._template_exists(("missing.html", "found.html"), loader, missing)
    assert not AdminModelAuditService._template_exists(
        ("missing.html",), Mock(side_effect=missing), missing
    )


def test_custom_template_check_counts_missing_and_accepts_existing(monkeypatch) -> None:
    from django.template import TemplateDoesNotExist

    monkeypatch.setattr(
        "django.template.loader.get_template",
        Mock(side_effect=TemplateDoesNotExist("missing")),
    )
    monkeypatch.setattr(checks_module, "logger", Mock())
    checker = _checker(
        model_admin=SimpleNamespace(
            change_list_template=["one.html", "two.html"],
            change_form_template=None,
        )
    )
    checker._check_custom_templates()
    assert checker._stats["template_errors"] == 1

    monkeypatch.setattr("django.template.loader.get_template", Mock(return_value=object()))
    found = _checker(
        model_admin=SimpleNamespace(
            change_list_template="found.html",
            change_form_template=None,
        )
    )
    found._check_custom_templates()
    assert found._messages == []


def test_query_count_reporting_covers_ok_warning_failure_and_duplicate_previews() -> None:
    checker = _checker()
    checker._report_query_count([])
    checker._report_query_count([{"sql": "SELECT 1"}] * 16)
    long_sql = "SELECT " + ("x" * 200)
    checker._report_query_count([{"sql": long_sql}] * 51)
    assert checker._stats["n_plus_one_warnings"] == 1
    assert checker._stats["n_plus_one_fails"] == 1
    assert any(message.text.endswith("...") for message in checker._messages)

    sensitive = _checker()
    sensitive._add_duplicate_query_details(
        [{"sql": "SELECT * FROM users WHERE email = 'secret@example.test' AND id = 123"}] * 2,
        limit=1,
    )
    rendered = " ".join(message.text for message in sensitive._messages)
    assert "secret@example.test" not in rendered
    assert "123" not in rendered
    assert "email = '?'" in rendered

    no_duplicates = _checker()
    no_duplicates._add_duplicate_query_details(
        [{"sql": f"SELECT field_{index}"} for index in range(16)], limit=5
    )
    assert no_duplicates._messages == []


def test_runtime_query_check_reports_success_non_success_and_transport_errors(monkeypatch) -> None:
    class QueryContext:
        captured_queries: list[dict[str, str]] = []

        def __init__(self, connection: object) -> None:
            self.connection = connection

        def __enter__(self) -> QueryContext:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr("django.urls.reverse", Mock(return_value="/admin/inventory/receiver/"))
    monkeypatch.setattr("django.test.utils.CaptureQueriesContext", QueryContext)
    reset = Mock()
    monkeypatch.setattr("django.db.reset_queries", reset)

    forbidden = _checker(
        client=SimpleNamespace(get=Mock(return_value=SimpleNamespace(status_code=403)))
    )
    forbidden._check_runtime_query_count()
    assert forbidden._messages[-1].severity == "error"

    successful = _checker(
        client=SimpleNamespace(get=Mock(return_value=SimpleNamespace(status_code=200)))
    )
    successful._check_runtime_query_count()
    assert successful._messages[-1].text.endswith("Queries: 0")

    secret = "offline-with-token=do-not-log"
    failing = _checker(client=SimpleNamespace(get=Mock(side_effect=RuntimeError(secret))))
    failing._check_runtime_query_count()
    assert failing._messages[-1].text == (
        "[ERROR] Performance check failed (RuntimeError); details redacted."
    )
    assert secret not in failing._messages[-1].text
    assert reset.call_count == 3
