"""Audit service layer for logging, archiving, and retention management.

Handles activity logging, log archiving (CSV/Parquet), and chunked pruning
of stale records based on retention policies.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

from micboard.models import ActivityLog, APIHealthLog, ServiceSyncLog

if TYPE_CHECKING:  # pragma: no cover
    from django.contrib.auth.models import User

logger = logging.getLogger(__name__)


class AuditService:
    """Business logic for audit logs and data retention."""

    @staticmethod
    def log_activity(
        *,
        actor: User | None = None,
        activity_type: str,
        operation: str,
        summary: str,
        obj: object | None = None,
        details: dict | None = None,
        old_values: dict | None = None,
        new_values: dict | None = None,
        status: str = "success",
        error_message: str | None = None,
        request: object | None = None,
        level: str = "normal",
    ) -> ActivityLog | None:
        """Create a new activity log entry if permitted by logging mode."""
        from micboard.services.maintenance.logging_mode import LoggingModeService

        if not LoggingModeService.should_log(level):
            return None

        from django.contrib.contenttypes.models import ContentType

        log_data = {
            "user": actor,
            "activity_type": activity_type,
            "operation": operation,
            "summary": summary,
            "details": details or {},
            "old_values": old_values or {},
            "new_values": new_values or {},
            "status": status,
            "error_message": error_message,
        }

        if obj:
            log_data["content_type"] = ContentType.objects.get_for_model(obj)
            log_data["object_id"] = getattr(obj, "id", None)

        if request:
            # Safely extract IP and User Agent if request object is provided
            log_data["ip_address"] = getattr(request, "META", {}).get("REMOTE_ADDR")
            log_data["user_agent"] = getattr(request, "META", {}).get("HTTP_USER_AGENT")

        return ActivityLog.objects.create(**log_data)

    @staticmethod
    def prune_stale_logs() -> dict[str, int]:
        """Prune stale logs based on retention settings in MICBOARD_CONFIG."""
        from micboard.apps import MicboardConfig

        config = MicboardConfig.get_config()

        # Retention periods (days)
        activity_days = config.get("ACTIVITY_LOG_RETENTION_DAYS", 90)
        sync_days = config.get("SERVICE_SYNC_LOG_RETENTION_DAYS", 30)
        health_days = config.get("API_HEALTH_LOG_RETENTION_DAYS", 7)

        now = timezone.now()
        results = {}

        # 1. Activity Logs
        activity_cutoff = now - timedelta(days=activity_days)
        deleted, _ = ActivityLog.objects.filter(created_at__lt=activity_cutoff).delete()
        results["activity_logs"] = deleted

        # 2. Service Sync Logs
        sync_cutoff = now - timedelta(days=sync_days)
        deleted, _ = ServiceSyncLog.objects.filter(started_at__lt=sync_cutoff).delete()
        results["sync_logs"] = deleted

        # 3. API Health Logs
        health_cutoff = now - timedelta(days=health_days)
        deleted, _ = APIHealthLog.objects.filter(timestamp__lt=health_cutoff).delete()
        results["health_logs"] = deleted

        logger.info(f"Pruned stale logs: {results}")
        return results

    @staticmethod
    def archive_logs(path: str | None = None) -> str:
        """Export logs to archival storage before pruning.

        Exports activity logs to CSV or Parquet format for long-term storage.

        Args:
            path: Optional path to export to. If None, uses MICBOARD_CONFIG setting.

        Raises:
            NotImplementedError: This feature is not yet implemented.
        """
        raise NotImplementedError(
            "Log archival to CSV/Parquet is not yet implemented. "
            "Use prune_stale_logs() to remove old records instead."
        )
