"""Model-level checks used by the Django admin audit service."""

from __future__ import annotations

import logging
import re
from collections import Counter
from collections.abc import Sequence
from typing import Any

from django.contrib.admin import ModelAdmin
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.test import Client

from micboard.services.maintenance.admin_audit_dtos import (
    AdminAuditMessage,
    AdminAuditOptions,
    AdminAuditStats,
    AdminModelAuditResult,
    AuditSeverity,
)
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

HTTP_OK = 200
QUERY_COUNT_WARNING = 15
QUERY_COUNT_FAIL = 50
SQL_PREVIEW_LENGTH = 150
SQL_STRING_LITERAL = re.compile(r"'(?:''|[^'])*'")
SQL_NUMBER_LITERAL = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?![\w.])")


class AdminModelAuditService:
    """Audit one registered model and its ``ModelAdmin`` configuration."""

    def __init__(
        self,
        *,
        model: type[models.Model],
        model_admin: ModelAdmin[Any],
        client: Client,
        options: AdminAuditOptions,
    ) -> None:
        """Initialize a model audit with its authenticated HTTP client."""
        self.model = model
        self.model_admin = model_admin
        self.client = client
        self.options = options
        self._messages: list[AdminAuditMessage] = []
        self._stats: Counter[str] = Counter(models_scanned=1)

    def audit(self) -> AdminModelAuditResult:
        """Run selected checks and return typed findings and counters."""
        run_all = not self.options.has_check_filter
        if run_all or self.options.check_unfold:
            self._check_unfold_inheritance()
            self._check_unfold_widgets()
            self._check_unfold_filters()
        if run_all or self.options.check_media:
            self._check_deprecated_media_class()
        if run_all or self.options.check_search_depth:
            self._check_search_depth()
        if run_all:
            self._check_custom_templates()
        if run_all or self.options.check_n1:
            self._check_static_query_optimization()
            if self.options.quick:
                self._add("  [PERF] Live query capture skipped in quick mode")
            else:
                self._check_runtime_query_count()

        return AdminModelAuditResult(
            app_label=self.model._meta.app_label,
            model_name=self.model.__name__,
            messages=tuple(self._messages),
            stats=AdminAuditStats.from_mapping(self._stats),
        )

    def _add(self, text: str, severity: AuditSeverity = "info") -> None:
        """Docstring."""
        self._messages.append(AdminAuditMessage(text=text, severity=severity))

    def _check_unfold_inheritance(self) -> None:
        """Docstring."""
        try:
            from unfold.admin import ModelAdmin as UnfoldModelAdmin
        except ImportError:
            self._add("  [CONF] Unfold is not installed", "error")
            self._stats["unfold_non_compliant"] += 1
            return

        if isinstance(self.model_admin, UnfoldModelAdmin):
            self._add("  [CONF] Inherits from UnfoldModelAdmin: YES")
            self._stats["unfold_compliant"] += 1
            return

        self._add(
            f"  [CONF] Inherits from UnfoldModelAdmin: NO ({type(self.model_admin).__name__})",
            "warning",
        )
        self._stats["unfold_non_compliant"] += 1

    def _check_unfold_widgets(self) -> None:
        """Docstring."""
        overrides = getattr(self.model_admin, "formfield_overrides", {})
        optimized = 0
        for override in overrides.values():
            widget = override.get("widget")
            widget_module = getattr(widget, "__module__", "")
            if widget is not None and widget_module.startswith("unfold.widgets"):
                optimized += 1
        if optimized:
            self._add(f"  [WIDG] Unfold widgets used: {optimized}")
            self._stats["widgets_optimized"] += 1

    def _check_unfold_filters(self) -> None:
        """Docstring."""
        configured_filters = getattr(self.model_admin, "list_filter", ())
        optimized = sum(
            1
            for configured_filter in configured_filters
            if isinstance(configured_filter, type)
            and configured_filter.__module__.startswith("unfold.contrib.filters")
        )
        if optimized:
            self._add(f"  [FILT] Unfold filters used: {optimized}")
            self._stats["filters_optimized"] += 1

    def _check_deprecated_media_class(self) -> None:
        """Docstring."""
        if "Media" not in type(self.model_admin).__dict__:
            return
        self._add(
            "  [MEDIA] ModelAdmin declares an inner Media class; use the project asset pipeline",
            "warning",
        )
        self._stats["media_warnings"] += 1

    def _check_search_depth(self) -> None:
        """Docstring."""
        search_fields = getattr(self.model_admin, "search_fields", ())
        deep_fields = [field for field in search_fields if isinstance(field, str) and "__" in field]
        if deep_fields:
            self._add(f"  [SRCH] Deep relationship lookups: {deep_fields}", "warning")
            self._stats["search_warnings"] += 1
        elif search_fields:
            self._add("  [SRCH] Search fields use local columns only")

    def _check_custom_templates(self) -> None:
        """Docstring."""
        from django.template import TemplateDoesNotExist
        from django.template.loader import get_template

        from micboard.utils.dependencies import HAS_ADMIN_SORTABLE, HAS_UNFOLD

        for attribute in ("change_list_template", "change_form_template"):
            configured = getattr(self.model_admin, attribute, None)
            if not configured or self._is_sortable_template(
                configured, HAS_UNFOLD, HAS_ADMIN_SORTABLE
            ):
                continue
            candidates = configured if isinstance(configured, list | tuple) else (configured,)
            if self._template_exists(candidates, get_template, TemplateDoesNotExist):
                continue
            self._add(f"  [TEMP] {attribute} NOT FOUND: {configured}", "error")
            self._stats["template_errors"] += 1

    @staticmethod
    def _is_sortable_template(configured: object, has_unfold: bool, has_sortable: bool) -> bool:
        """Return whether a configured template belongs to the known integration override."""
        if not has_unfold or not has_sortable:
            return False
        candidates = configured if isinstance(configured, list | tuple) else (configured,)
        return any("adminsortable2" in str(candidate) for candidate in candidates)

    @staticmethod
    def _template_exists(
        candidates: Sequence[object],
        loader: Any,
        missing_error: type[Exception],
    ) -> bool:
        """Return whether at least one configured template can be loaded."""
        for candidate in candidates:
            try:
                loader(candidate)
            except missing_error:
                logger.debug("Admin template candidate not found: %s", candidate)
            else:
                return True
        return False

    def _check_static_query_optimization(self) -> None:
        """Docstring."""
        relational_fields: list[str] = []
        for field_name in getattr(self.model_admin, "list_display", ()):
            if not isinstance(field_name, str):
                continue
            try:
                field = self.model._meta.get_field(field_name)
            except FieldDoesNotExist:
                continue
            if field.is_relation and (field.many_to_one or field.one_to_one):
                relational_fields.append(field_name)

        has_optimization = bool(
            getattr(self.model_admin, "list_select_related", False)
            or getattr(self.model_admin, "list_prefetch_related", ())
        )
        if relational_fields and not has_optimization:
            self._add(
                f"  [PERF] Relational list fields {relational_fields} have no eager loading",
                "warning",
            )

    def _check_runtime_query_count(self) -> None:
        """Docstring."""
        from django.db import connection, reset_queries
        from django.test.utils import CaptureQueriesContext
        from django.urls import reverse

        try:
            url = reverse(
                f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"
            )
            with CaptureQueriesContext(connection) as context:
                response = self.client.get(url)
            if response.status_code != HTTP_OK:
                self._add(f"  [FAIL] List View: {response.status_code}", "error")
                return
            self._report_query_count(context.captured_queries)
        except Exception as exc:
            logger.exception(
                "Admin runtime performance check failed",
                exc_info=sanitized_exception_info(exc),
            )
            self._add(
                f"  [ERROR] Performance check failed ({type(exc).__name__}); details redacted.",
                "error",
            )
        finally:
            reset_queries()

    def _report_query_count(self, queries: Sequence[dict[str, str]]) -> None:
        """Docstring."""
        query_count = len(queries)
        message = f"  [PERF] List View Queries: {query_count}"
        if query_count > QUERY_COUNT_FAIL:
            self._add(f"{message} - HIGH QUERY COUNT DETECTED!", "error")
            self._stats["n_plus_one_fails"] += 1
            self._add_duplicate_query_details(queries, limit=10)
        elif query_count > QUERY_COUNT_WARNING:
            self._add(f"{message} - WARNING", "warning")
            self._stats["n_plus_one_warnings"] += 1
            self._add_duplicate_query_details(queries, limit=5)
        else:
            self._add(message)

    def _add_duplicate_query_details(
        self,
        queries: Sequence[dict[str, str]],
        *,
        limit: int,
    ) -> None:
        """Docstring."""
        sql_counts = Counter(self._redact_sql_literals(query["sql"]) for query in queries)
        duplicates = sorted(
            ((sql, count) for sql, count in sql_counts.items() if count > 1),
            key=lambda item: item[1],
            reverse=True,
        )
        if not duplicates:
            return
        self._add(f"       Found {len(duplicates)} duplicated query types", "warning")
        for sql, count in duplicates[:limit]:
            preview = sql[:SQL_PREVIEW_LENGTH]
            if len(sql) > SQL_PREVIEW_LENGTH:
                preview += "..."
            self._add(f"       {count}x: {preview}")

    @staticmethod
    def _redact_sql_literals(sql: str) -> str:
        """Normalize query values so audit output cannot disclose row data."""
        redacted = SQL_STRING_LITERAL.sub("'?'", sql)
        redacted = SQL_NUMBER_LITERAL.sub("?", redacted)
        return " ".join(redacted.split())
