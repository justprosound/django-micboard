"""Bounded audit persistence for manufacturer polling runs."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from django.db import DEFAULT_DB_ALIAS
from django.utils import timezone

from pydantic import Field

from micboard.services.shared.base_dto import PydanticBaseDTO
from micboard.services.sync.polling_dtos import ManufacturerSyncResult
from micboard.utils.exception_logging import sanitized_exception_info

if TYPE_CHECKING:
    from micboard.models.audit.activity_log import ServiceSyncLog
    from micboard.models.discovery.manufacturer import Manufacturer

logger = logging.getLogger(__name__)


class ServiceSyncAuditDTO(PydanticBaseDTO):
    """Secret-free facts persisted for one manufacturer polling run."""

    started_at: datetime
    completed_at: datetime
    status: Literal["success", "failed"]
    device_count: int = Field(ge=0)
    created_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    device_limit: int | None = Field(default=None, ge=1)
    inventory_complete: bool = True

    @classmethod
    def from_poll_result(
        cls,
        *,
        started_at: datetime,
        result: ManufacturerSyncResult,
    ) -> ServiceSyncAuditDTO:
        """Build an audit record from one manufacturer inventory sync outcome."""
        error_count = len(result.errors)
        return cls(
            started_at=started_at,
            completed_at=timezone.now(),
            status="failed" if error_count else "success",
            device_count=max(0, result.devices_examined),
            created_count=max(0, result.devices_added),
            updated_count=max(0, result.devices_updated),
            error_count=error_count,
            device_limit=result.device_limit,
            inventory_complete=result.inventory_complete,
        )


class ServiceSyncAuditService:
    """Persist polling audit rows without affecting the polling outcome."""

    @staticmethod
    def record_poll_result(
        *,
        manufacturer: Manufacturer,
        started_at: datetime,
        result: ManufacturerSyncResult,
    ) -> ServiceSyncLog | None:
        """Record one bounded run, containing and redacting audit failures."""
        from micboard.models.audit.activity_log import ServiceSyncLog

        try:
            audit = ServiceSyncAuditDTO.from_poll_result(
                started_at=started_at,
                result=result,
            )
            using = manufacturer._state.db or DEFAULT_DB_ALIAS
            return ServiceSyncLog.objects.using(using).create(
                service=manufacturer,
                sync_type="full",
                started_at=audit.started_at,
                completed_at=audit.completed_at,
                device_count=audit.device_count,
                online_count=0,
                offline_count=0,
                updated_count=audit.updated_count,
                status=audit.status,
                error_message=(
                    f"Polling reported {audit.error_count} error(s); details redacted."
                    if audit.error_count
                    else ""
                ),
                details={
                    "created_count": audit.created_count,
                    "device_limit": audit.device_limit,
                    "inventory_complete": audit.inventory_complete,
                },
            )
        except Exception as exc:
            logger.exception(
                "Failed to record manufacturer sync audit for manufacturer %s",
                manufacturer.pk,
                exc_info=sanitized_exception_info(exc),
            )
            return None
