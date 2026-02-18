"""Structured logging utilities for standardized logging across the application.

Provides helpers for logging CRUD operations, service activities, and syncs.
"""

from __future__ import annotations

import logging
from typing import Any

from django.contrib.auth.models import User
from django.db import models

from micboard.models.audit.activity_log import ActivityLog, ServiceSyncLog

# Get logger for this module
logger = logging.getLogger("micboard.logging")


class StructuredLogger:
    """Utility class for structured logging with activity tracking.

    Logs to both Python logging and ActivityLog models.
    """

    @staticmethod
    def log_crud_create(
        obj: models.Model,
        *,
        user: User | None = None,
        new_values: dict[str, Any] | None = None,
        request=None,
        extra: dict[str, Any] | None = None,
    ) -> ActivityLog:
        """Log a CREATE operation.

        Args:
            obj: The created object
            user: User performing the operation
            new_values: Values of created object
            request: Optional HTTP request
            extra: Extra context for logging
        """
        values = new_values or {}
        log = ActivityLog.log_crud(
            operation=ActivityLog.CREATE,
            obj=obj,
            user=user,
            new_values=values,
            request=request,
        )

        log_data = extra or {}
        log_data["model"] = obj.__class__.__name__
        log_data["id"] = obj.pk
        log_data["summary"] = str(obj)[:100]

        logger.info(
            f"Created {obj.__class__.__name__}",
            extra=log_data,
        )

        return log

    @staticmethod
    def log_crud_update(
        obj: models.Model,
        *,
        user: User | None = None,
        old_values: dict[str, Any] | None = None,
        new_values: dict[str, Any] | None = None,
        request=None,
        extra: dict[str, Any] | None = None,
    ) -> ActivityLog:
        """Log an UPDATE operation.

        Args:
            obj: The updated object
            user: User performing the operation
            old_values: Previous values
            new_values: New values
            request: Optional HTTP request
            extra: Extra context for logging
        """
        log = ActivityLog.log_crud(
            operation=ActivityLog.UPDATE,
            obj=obj,
            user=user,
            old_values=old_values or {},
            new_values=new_values or {},
            request=request,
        )

        log_data = extra or {}
        log_data["model"] = obj.__class__.__name__
        log_data["id"] = obj.pk
        log_data["changes"] = (
            set(new_values.keys()) - set(old_values.keys() or [])
            if new_values and old_values
            else []
        )

        logger.info(
            f"Updated {obj.__class__.__name__}",
            extra=log_data,
        )

        return log

    @staticmethod
    def log_crud_delete(
        obj: models.Model,
        *,
        user: User | None = None,
        old_values: dict[str, Any] | None = None,
        request=None,
        extra: dict[str, Any] | None = None,
    ) -> ActivityLog:
        """Log a DELETE operation.

        Args:
            obj: The deleted object
            user: User performing the operation
            old_values: Values of deleted object
            request: Optional HTTP request
            extra: Extra context for logging
        """
        log = ActivityLog.log_crud(
            operation=ActivityLog.DELETE,
            obj=obj,
            user=user,
            old_values=old_values or {},
            request=request,
        )

        log_data = extra or {}
        log_data["model"] = obj.__class__.__name__
        log_data["id"] = obj.pk
        log_data["summary"] = str(obj)[:100]

        logger.info(
            f"Deleted {obj.__class__.__name__}",
            extra=log_data,
        )

        return log

    @staticmethod
    def log_service_start(
        service_code: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ActivityLog:
        """Log service startup."""
        log = ActivityLog.log_service(
            operation=ActivityLog.START,
            service_code=service_code,
            summary="Service started",
            status="success",
        )

        log_data = extra or {}
        log_data["service"] = service_code
        logger.info(
            f"Service started: {service_code}",
            extra=log_data,
        )

        return log

    @staticmethod
    def log_service_stop(
        service_code: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ActivityLog:
        """Log service shutdown."""
        log = ActivityLog.log_service(
            operation=ActivityLog.STOP,
            service_code=service_code,
            summary="Service stopped",
            status="success",
        )

        log_data = extra or {}
        log_data["service"] = service_code
        logger.info(
            f"Service stopped: {service_code}",
            extra=log_data,
        )

        return log

    @staticmethod
    def log_service_error(
        service_code: str,
        error: Exception,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ActivityLog:
        """Log service error."""
        log = ActivityLog.log_service(
            operation=ActivityLog.FAILURE,
            service_code=service_code,
            summary="Service error",
            status="failed",
            error_message=str(error),
        )

        log_data = extra or {}
        log_data["service"] = service_code
        log_data["error"] = str(error)

        logger.error(
            f"Service error in {service_code}",
            extra=log_data,
            exc_info=True,
        )

        return log

    @staticmethod
    def log_sync_start(
        service_code: str,
        sync_type: str = "full",
        *,
        extra: dict[str, Any] | None = None,
    ) -> ServiceSyncLog:
        """Log sync start."""
        from django.utils import timezone

        from micboard.models import Manufacturer

        manufacturer = Manufacturer.objects.filter(code=service_code).first()
        if not manufacturer:
            logger.warning(f"Manufacturer not found for {service_code}")
            return None

        log = ServiceSyncLog.objects.create(
            service=manufacturer,
            sync_type=sync_type,
            started_at=timezone.now(),
            status="success",
        )

        log_data = extra or {}
        log_data["service"] = service_code
        log_data["sync_type"] = sync_type

        logger.info(
            f"Sync started: {service_code} ({sync_type})",
            extra=log_data,
        )

        return log

    @staticmethod
    def log_sync_complete(
        sync_log: ServiceSyncLog,
        device_count: int = 0,
        online_count: int = 0,
        offline_count: int = 0,
        updated_count: int = 0,
        *,
        error_message: str = "",
        extra: dict[str, Any] | None = None,
    ) -> ServiceSyncLog:
        """Log sync completion.

        Args:
            sync_log: ServiceSyncLog instance to update
            device_count: Total devices processed
            online_count: Devices now online
            offline_count: Devices now offline
            updated_count: Devices updated
            error_message: Error if failed
            extra: Extra context
        """
        from django.utils import timezone

        sync_log.completed_at = timezone.now()
        sync_log.device_count = device_count
        sync_log.online_count = online_count
        sync_log.offline_count = offline_count
        sync_log.updated_count = updated_count

        if error_message:
            sync_log.status = "failed"
            sync_log.error_message = error_message
        else:
            sync_log.status = "success"

        sync_log.save()

        log_data = extra or {}
        log_data["service"] = sync_log.service.code
        log_data["sync_type"] = sync_log.sync_type
        log_data["device_count"] = device_count
        log_data["online_count"] = online_count
        log_data["duration_seconds"] = sync_log.duration_seconds()
        log_data["status"] = sync_log.status

        level = logging.ERROR if error_message else logging.INFO
        logger.log(
            level,
            f"Sync completed: {sync_log.service.code} ({sync_log.get_sync_type_display()})",
            extra=log_data,
        )

        return sync_log


def get_structured_logger() -> StructuredLogger:
    """Get structured logger instance."""
    return StructuredLogger()
