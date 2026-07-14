"""Signal handlers for manufacturer lifecycle events.

Provides audit logging and discovery trigger side-effects
when manufacturers are created, updated, or deleted.
"""

from __future__ import annotations

import logging

from micboard.models.audit import ActivityLog

logger = logging.getLogger(__name__)


def handle_manufacturer_save(*, manufacturer, created: bool, old_active: bool | None) -> bool:
    """Perform side-effects after a Manufacturer is saved.

    - Emits audit ActivityLog entries
    - Triggers discovery when a manufacturer is toggled active
    """
    from django.contrib.contenttypes.models import ContentType

    try:
        if created:
            ActivityLog.objects.create(
                activity_type=ActivityLog.ACTIVITY_CRUD,
                operation=ActivityLog.CREATE,
                content_type=ContentType.objects.get_for_model(manufacturer),
                object_id=manufacturer.pk,
                summary=f"Created manufacturer: {manufacturer.name}",
                details={"name": manufacturer.name, "code": manufacturer.code},
            )
        else:
            ActivityLog.objects.create(
                activity_type=ActivityLog.ACTIVITY_CRUD,
                operation=ActivityLog.UPDATE,
                content_type=ContentType.objects.get_for_model(manufacturer),
                object_id=manufacturer.pk,
                summary=f"Modified manufacturer: {manufacturer.name}",
                details={
                    "name": manufacturer.name,
                    "code": manufacturer.code,
                    "is_active": manufacturer.is_active,
                },
            )
    except Exception:
        logger.exception("Failed to write activity log for manufacturer %s", manufacturer.pk)

    return (not created) and manufacturer.is_active and not bool(old_active)


def handle_manufacturer_delete(*, manufacturer) -> None:
    """Perform side-effects after Manufacturer deletion (audit/log)."""
    try:
        ActivityLog.objects.create(
            activity_type=ActivityLog.ACTIVITY_CRUD,
            operation="deleted",
            summary=f"Deleted {manufacturer.__class__.__name__}: {manufacturer.name}",
            object_id=str(manufacturer.pk) if manufacturer.pk else None,
            details={
                "name": manufacturer.name,
                "code": manufacturer.code,
                "model_name": manufacturer.__class__.__name__,
            },
        )
    except Exception:
        logger.exception(
            "Failed to write delete activity log for manufacturer %s",
            manufacturer.pk,
        )
