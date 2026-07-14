"""Audit the live Django admin registry for configuration and query risks."""

from __future__ import annotations

import os
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from micboard.exceptions import AdminAuditSetupError
from micboard.services.maintenance.admin_audit_dtos import (
    MAX_ADMIN_AUDIT_THREADS,
    AdminAuditOptions,
    AdminAuditReport,
)
from micboard.services.maintenance.admin_audit_service import AdminAuditService


class Command(BaseCommand):
    """Expose the admin audit service through Django's command interface."""

    help = "Audits the Django Admin for Unfold compliance, N+1 issues, and best practices."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register the supported audit filters and check selectors."""
        parser.add_argument("--app", type=str, help="Filter by app label")
        parser.add_argument(
            "--model",
            type=str,
            nargs="+",
            help="Filter by model name (e.g. Charger or micboard.Charger)",
        )
        parser.add_argument("--exclude", type=str, nargs="+", help="Exclude models by name")
        parser.add_argument(
            "--errors-only",
            action="store_true",
            help="Only show models with errors or warnings",
        )
        parser.add_argument(
            "--quick",
            action="store_true",
            help="Skip live HTTP query capture to speed up the audit",
        )
        parser.add_argument(
            "--check-n1",
            action="store_true",
            help="Only check for N+1 query issues (skips other checks)",
        )
        parser.add_argument(
            "--check-unfold",
            action="store_true",
            help="Only check Unfold compliance (inheritance, widgets, filters)",
        )
        parser.add_argument(
            "--check-media",
            action="store_true",
            help="Only check for deprecated Media classes",
        )
        parser.add_argument(
            "--check-search-depth",
            action="store_true",
            help="Check for deep FK lookups in search_fields",
        )
        parser.add_argument(
            "--threads",
            type=int,
            default=min(MAX_ADMIN_AUDIT_THREADS, (os.cpu_count() or 1) * 4),
            help=f"Parallel audit workers (default: CPUs * 4; maximum: {MAX_ADMIN_AUDIT_THREADS})",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Validate options, run the service, and render its typed report."""
        audit_options = self._build_options(options)
        if not audit_options.errors_only:
            self.stdout.write("Starting Micboard Admin Audit...")
            self.stdout.write("===============================")

        original_debug = settings.DEBUG
        original_allowed_hosts = settings.ALLOWED_HOSTS
        settings.DEBUG = False
        if "testserver" not in original_allowed_hosts:
            settings.ALLOWED_HOSTS = [*original_allowed_hosts, "testserver"]
        try:
            if original_debug:
                self.stdout.write("Forcing DEBUG=False for audit duration (memory safety).")
            report = AdminAuditService().run(audit_options)
        except AdminAuditSetupError as exc:
            raise CommandError(
                f"Admin audit setup failed ({type(exc).__name__}); details redacted."
            ) from exc
        finally:
            settings.DEBUG = original_debug
            settings.ALLOWED_HOSTS = original_allowed_hosts

        self._write_report(report)

    @staticmethod
    def _build_options(options: dict[str, Any]) -> AdminAuditOptions:
        try:
            return AdminAuditOptions(
                app_label=options.get("app"),
                model_names=tuple(str(name) for name in (options.get("model") or ())),
                excluded_names=tuple(str(name) for name in (options.get("exclude") or ())),
                errors_only=bool(options.get("errors_only")),
                quick=bool(options.get("quick")),
                check_n1=bool(options.get("check_n1")),
                check_unfold=bool(options.get("check_unfold")),
                check_media=bool(options.get("check_media")),
                check_search_depth=bool(options.get("check_search_depth")),
                threads=options.get("threads", 1),
            )
        except ValueError as exc:
            raise CommandError(
                f"Invalid admin audit options ({type(exc).__name__}); details redacted."
            ) from exc

    def _write_report(self, report: AdminAuditReport) -> None:
        for message in report.messages:
            style = {
                "error": self.style.ERROR,
                "warning": self.style.WARNING,
            }.get(message.severity)
            self.stdout.write(style(message.text) if style else message.text)
        if report.matched_models:
            self._write_summary(report)

    def _write_summary(self, report: AdminAuditReport) -> None:
        stats = report.stats
        self.stdout.write("\n\n===============================")
        self.stdout.write("       AUDIT SUMMARY")
        self.stdout.write("===============================")
        self.stdout.write(f"Total Models Scanned:   {stats.models_scanned}")
        self.stdout.write(f"Unfold Compliant:       {stats.unfold_compliant}")
        self.stdout.write(f"Unfold Non-Compliant:   {stats.unfold_non_compliant}")
        self.stdout.write(f"N+1 Warnings (>15 q):   {stats.n_plus_one_warnings}")
        self.stdout.write(f"N+1 Failures (>50 q):   {stats.n_plus_one_fails}")
        self.stdout.write(f"Template Errors:        {stats.template_errors}")
        self.stdout.write("===============================")
