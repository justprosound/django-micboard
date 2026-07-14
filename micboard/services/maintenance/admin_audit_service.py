"""Orchestration service for reusable Django admin audits."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.conf import settings
from django.contrib import admin
from django.contrib.admin import ModelAdmin
from django.contrib.auth import get_user_model
from django.db import connections, models, reset_queries
from django.test import Client
from django.urls import reverse

from micboard.services.maintenance.admin_audit_checks import AdminModelAuditService
from micboard.services.maintenance.admin_audit_dtos import (
    AdminAuditMessage,
    AdminAuditOptions,
    AdminAuditReport,
    AdminAuditStats,
    AdminModelAuditResult,
)
from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

Registry = Mapping[type[models.Model], ModelAdmin]
RegistryEntry = tuple[type[models.Model], ModelAdmin]


class AdminAuditSetupError(RuntimeError):
    """Raised when the live admin cannot be audited safely."""


class AdminAuditService:
    """Select registered models and coordinate independent model audits."""

    def run(
        self,
        options: AdminAuditOptions,
        *,
        registry: Registry | None = None,
        user: Any | None = None,
    ) -> AdminAuditReport:
        """Run the configured audit without creating or modifying user accounts."""
        resolved_registry = admin.site._registry if registry is None else registry
        if not resolved_registry:
            return AdminAuditReport(
                messages=(AdminAuditMessage(text="No models registered in admin."),)
            )

        audit_user = user if user is not None else self._find_audit_user()
        client = self._authenticated_client(audit_user)
        try:
            messages: list[AdminAuditMessage] = []
            if not options.model_names:
                messages.extend(self._check_index(client))
                messages.extend(self._check_unfold_settings())

            selected = self.select_models(resolved_registry, options)
            if not selected:
                messages.append(AdminAuditMessage(text="No models matched the filter."))
                return AdminAuditReport(messages=tuple(messages))

            results = self._audit_models(selected, audit_user, options, client=client)
            counters: Counter[str] = Counter()
            for result in results:
                counters.update(result.stats.model_dump())
                if options.errors_only and not result.has_issues:
                    continue
                messages.append(
                    AdminAuditMessage(text=f"\n--- {result.app_label}.{result.model_name} ---")
                )
                messages.extend(result.messages)

            return AdminAuditReport(
                messages=tuple(messages),
                stats=AdminAuditStats.from_mapping(counters),
                matched_models=len(selected),
            )
        finally:
            self._logout_client(client)

    def select_models(self, registry: Registry, options: AdminAuditOptions) -> list[RegistryEntry]:
        """Return deterministic registry entries matching CLI filters."""
        return sorted(
            (
                (model, model_admin)
                for model, model_admin in registry.items()
                if self._model_is_selected(model, options)
            ),
            key=lambda entry: (entry[0]._meta.app_label, entry[0]._meta.model_name),
        )

    @staticmethod
    def _model_is_selected(model: type[models.Model], options: AdminAuditOptions) -> bool:
        app_label = model._meta.app_label
        model_name = model.__name__
        full_name = f"{app_label}.{model_name}"
        if options.app_label and app_label != options.app_label:
            return False
        if model_name in options.excluded_names or full_name in options.excluded_names:
            return False
        if options.model_names:
            return model_name in options.model_names or full_name in options.model_names
        return True

    @staticmethod
    def _find_audit_user() -> Any:
        user_model = get_user_model()
        user = user_model._default_manager.filter(is_active=True, is_superuser=True).first()
        if user is None:
            raise AdminAuditSetupError(
                "Admin audit requires an existing active superuser; no account was created."
            )
        return user

    @staticmethod
    def _authenticated_client(user: Any) -> Client:
        client = Client()
        try:
            client.force_login(user)
        except Exception as exc:
            logger.exception(
                "Could not authenticate the admin audit client",
                exc_info=sanitized_exception_info(exc),
            )
            raise AdminAuditSetupError(
                f"Could not authenticate admin audit user ({type(exc).__name__}); details redacted."
            ) from exc
        return client

    @staticmethod
    def _logout_client(client: Client) -> None:
        """Delete the privileged audit session without masking audit results."""
        try:
            client.logout()
        except Exception as exc:
            logger.exception(
                "Could not clean up an admin audit client session",
                exc_info=sanitized_exception_info(exc),
            )

    def _audit_models(
        self,
        entries: Sequence[RegistryEntry],
        user: Any,
        options: AdminAuditOptions,
        *,
        client: Client | None = None,
    ) -> list[AdminModelAuditResult]:
        if options.threads == 1:
            return [
                self._audit_model_safely(entry, user, options, client=client) for entry in entries
            ]
        with ThreadPoolExecutor(max_workers=options.threads) as executor:
            return list(
                executor.map(
                    lambda entry: self._audit_model_safely(entry, user, options),
                    entries,
                )
            )

    def _audit_model_safely(
        self,
        entry: RegistryEntry,
        user: Any,
        options: AdminAuditOptions,
        *,
        client: Client | None = None,
    ) -> AdminModelAuditResult:
        model, model_admin = entry
        owns_client = client is None
        audit_client = client
        try:
            if audit_client is None:
                audit_client = self._authenticated_client(user)
            return AdminModelAuditService(
                model=model,
                model_admin=model_admin,
                client=audit_client,
                options=options,
            ).audit()
        except Exception as exc:
            logger.exception(
                "Admin audit failed for %s.%s",
                model._meta.app_label,
                model._meta.model_name,
                exc_info=sanitized_exception_info(exc),
            )
            return AdminModelAuditResult(
                app_label=model._meta.app_label,
                model_name=model.__name__,
                messages=(
                    AdminAuditMessage(
                        text=(
                            "  [CRITICAL ERROR] Worker failed "
                            f"({type(exc).__name__}); details redacted."
                        ),
                        severity="error",
                    ),
                ),
                stats=AdminAuditStats(models_scanned=1),
            )
        finally:
            if owns_client and audit_client is not None:
                self._logout_client(audit_client)
            reset_queries()
            connections.close_all()

    @staticmethod
    def _check_index(client: Client) -> list[AdminAuditMessage]:
        try:
            response = client.get(reverse("admin:index"))
        except Exception as exc:
            logger.exception(
                "Admin index audit failed",
                exc_info=sanitized_exception_info(exc),
            )
            return [
                AdminAuditMessage(
                    text=(f"[ERROR] Admin Index ({type(exc).__name__}); details redacted."),
                    severity="error",
                )
            ]
        if response.status_code != 200:
            return [
                AdminAuditMessage(
                    text=f"[FAIL] Admin Index: {response.status_code}",
                    severity="error",
                )
            ]
        messages = [AdminAuditMessage(text="[PASS] Admin Index")]
        if b"unfold" in response.content.lower():
            messages.append(AdminAuditMessage(text="       - Unfold theme detected"))
        else:
            messages.append(
                AdminAuditMessage(
                    text="       - Unfold theme markers NOT detected in index",
                    severity="warning",
                )
            )
        return messages

    @staticmethod
    def _check_unfold_settings() -> list[AdminAuditMessage]:
        if getattr(settings, "UNFOLD", {}):
            return [AdminAuditMessage(text="  [PASS] UNFOLD settings found")]
        return [
            AdminAuditMessage(
                text="  [FAIL] UNFOLD settings not found!",
                severity="error",
            )
        ]
