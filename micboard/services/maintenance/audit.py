"""Audit service layer for logging, archiving, and retention management.

Handles activity logging, log archiving (CSV/Parquet), and chunked pruning
of stale records based on retention policies.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.http import HttpRequest
from django.utils import timezone

from micboard.models.audit.activity_log import ActivityLog, ServiceSyncLog
from micboard.models.telemetry.health import APIHealthLog
from micboard.services.maintenance.logging_mode import LoggingModeService, LogMode
from micboard.services.manufacturer.secret_redaction import redact_secrets

logger = logging.getLogger(__name__)


def _json_safe(value: dict[str, Any] | None) -> dict[str, Any]:
    """Return redacted JSON-compatible audit metadata."""
    redacted = redact_secrets(value or {})
    return json.loads(json.dumps(redacted, cls=DjangoJSONEncoder))


class AuditService:
    """Business logic for audit logs and data retention."""

    @staticmethod
    def log_activity(
        *,
        actor: Any = None,
        activity_type: str,
        operation: str,
        summary: str,
        obj: models.Model | None = None,
        details: dict | None = None,
        old_values: dict | None = None,
        new_values: dict | None = None,
        status: str = "success",
        error_message: str | None = None,
        request: HttpRequest | None = None,
        log_mode: LogMode = "normal",
        using: str = "default",
    ) -> ActivityLog | None:
        """Create an activity log entry when the configured log mode permits it."""
        if not LoggingModeService.should_log(log_mode):
            return None

        from django.contrib.contenttypes.models import ContentType

        log_data: dict[str, Any] = {
            "user": actor,
            "activity_type": activity_type,
            "operation": operation,
            "summary": summary[:255],
            "details": _json_safe(details),
            "old_values": _json_safe(old_values),
            "new_values": _json_safe(new_values),
            "status": status,
            "error_message": error_message or "",
        }

        if obj:
            log_data["content_type"] = ContentType.objects.db_manager(using).get_for_model(obj)
            log_data["object_id"] = obj.pk

        if request:
            # Safely extract IP and User Agent if request object is provided
            log_data["ip_address"] = getattr(request, "META", {}).get("REMOTE_ADDR")
            log_data["user_agent"] = (getattr(request, "META", {}).get("HTTP_USER_AGENT") or "")[
                :255
            ]

        return ActivityLog.objects.using(using).create(**log_data)

    @staticmethod
    def archive_activity_logs(
        *,
        retention_days: int | None = None,
        path: str | None = None,
    ) -> dict[str, int | str]:
        """Archive expired activity logs to CSV, then delete archived rows.

        The CSV is completed before database deletion, so an I/O failure cannot
        discard audit records. JSON fields are serialized explicitly for a stable,
        portable archive format.
        """
        from micboard.services.settings.settings_service import settings

        days = AuditService._resolve_retention_days(
            retention_days,
            default=settings.activity_log_retention_days,
        )
        cutoff = timezone.now() - timedelta(days=days)
        queryset = ActivityLog.objects.filter(created_at__lt=cutoff).order_by("created_at", "pk")
        log_ids = list(queryset.values_list("pk", flat=True))

        archive_directory = Path(path or settings.audit_archive_path).expanduser()
        archive_directory.mkdir(parents=True, exist_ok=True)
        timestamp = timezone.now().strftime("%Y%m%dT%H%M%S%f")
        archive_file = archive_directory / f"activity-logs-{timestamp}.csv"

        field_names = [
            "id",
            "activity_type",
            "operation",
            "user_id",
            "service_code",
            "content_type_id",
            "object_id",
            "summary",
            "details",
            "old_values",
            "new_values",
            "status",
            "error_message",
            "created_at",
            "updated_at",
            "ip_address",
            "user_agent",
        ]
        with archive_file.open("x", encoding="utf-8", newline="") as archive_stream:
            writer = csv.DictWriter(archive_stream, fieldnames=field_names)
            writer.writeheader()
            for record in queryset.values(*field_names):
                row = dict(record)
                for field_name in ("details", "old_values", "new_values"):
                    row[field_name] = json.dumps(
                        row[field_name],
                        cls=DjangoJSONEncoder,
                        sort_keys=True,
                    )
                writer.writerow(row)

        if log_ids:
            ActivityLog.objects.filter(pk__in=log_ids).delete()

        logger.info("Archived %d activity logs to %s", len(log_ids), archive_file)
        return {"archived": len(log_ids), "file": str(archive_file)}

    @staticmethod
    def prune_service_sync_logs(*, retention_days: int | None = None) -> int:
        """Delete expired service-sync logs and return deleted row count."""
        from micboard.services.settings.settings_service import settings

        days = AuditService._resolve_retention_days(
            retention_days,
            default=settings.service_sync_log_retention_days,
        )
        cutoff = timezone.now() - timedelta(days=days)
        deleted, _ = ServiceSyncLog.objects.filter(started_at__lt=cutoff).delete()
        return deleted

    @staticmethod
    def prune_api_health_logs(*, retention_days: int | None = None) -> int:
        """Delete expired API-health logs and return deleted row count."""
        from micboard.services.settings.settings_service import settings

        days = AuditService._resolve_retention_days(
            retention_days,
            default=settings.api_health_log_retention_days,
        )
        cutoff = timezone.now() - timedelta(days=days)
        deleted, _ = APIHealthLog.objects.filter(timestamp__lt=cutoff).delete()
        return deleted

    @staticmethod
    def _resolve_retention_days(retention_days: int | None, *, default: int) -> int:
        """Resolve and validate a retention period."""
        days = default if retention_days is None else retention_days
        if days < 0:
            raise ValueError("retention_days must be zero or greater")
        return days
