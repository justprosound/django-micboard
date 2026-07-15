"""Signal handlers for manufacturer lifecycle events.

Provides audit logging and discovery trigger side-effects
when manufacturers are created, updated, or deleted.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from micboard.utils.exception_logging import sanitized_exception_info

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from micboard.models.discovery.manufacturer import Manufacturer


def handle_manufacturer_save(
    *,
    manufacturer: Manufacturer,
    created: bool,
    old_active: bool | None,
    using: str = "default",
) -> bool:
    """Perform side-effects after a Manufacturer is saved.

    - Emits audit ActivityLog entries
    - Triggers discovery when a manufacturer is toggled active
    """
    from micboard.services.maintenance.audit import AuditService

    try:
        operation = "create" if created else "update"
        AuditService.log_activity(
            activity_type="crud",
            operation=operation,
            obj=manufacturer,
            summary=f"{operation.title()}d manufacturer: {manufacturer.name}",
            details={
                "name": manufacturer.name,
                "code": manufacturer.code,
                "is_active": manufacturer.is_active,
            },
            using=using,
        )
    except Exception as exc:
        logger.exception(
            "Failed to write activity log for manufacturer %s",
            manufacturer.pk,
            exc_info=sanitized_exception_info(exc),
        )

    return (not created) and manufacturer.is_active and not bool(old_active)


def handle_manufacturer_delete(
    *,
    manufacturer: Manufacturer,
    using: str = "default",
) -> None:
    """Perform side-effects after Manufacturer deletion (audit/log)."""
    from micboard.services.maintenance.audit import AuditService

    try:
        AuditService.log_activity(
            activity_type="crud",
            operation="delete",
            obj=manufacturer,
            summary=f"Deleted {manufacturer.__class__.__name__}: {manufacturer.name}",
            details={
                "name": manufacturer.name,
                "code": manufacturer.code,
                "model_name": manufacturer.__class__.__name__,
            },
            using=using,
        )
    except Exception as exc:
        logger.exception(
            "Failed to write delete activity log for manufacturer %s",
            manufacturer.pk,
            exc_info=sanitized_exception_info(exc),
        )
