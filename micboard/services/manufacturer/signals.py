"""Signal handlers for manufacturer lifecycle events.

Provides audit logging and discovery trigger side-effects
when manufacturers are created, updated, or deleted.
"""

from __future__ import annotations

import logging

from micboard.models.audit import ActivityLog

logger = logging.getLogger(__name__)


def handle_manufacturer_save(*, manufacturer, created: bool, old_active: bool | None) -> None:
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

    if (not created) and manufacturer.is_active and not old_active:
        from micboard.utils.dependencies import HAS_DJANGO_Q

        if HAS_DJANGO_Q:
            try:
                from django_q.tasks import async_task

                from micboard.tasks.sync.discovery import (
                    run_manufacturer_discovery_task,
                )

                async_task(
                    run_manufacturer_discovery_task,
                    manufacturer.pk,
                    False,
                    False,
                )
            except Exception:
                logger.exception("Failed to trigger discovery on manufacturer activation")
        else:
            logger.debug("Django-Q not installed; skipping discovery task trigger")


def save_manufacturer(manufacturer, *args, **kwargs) -> None:
    """Persist Manufacturer and perform side-effects.

    Handles the full save lifecycle: computes created/old_active state,
    calls the base save, then performs audit logging and discovery triggers.
    """
    from micboard.models.discovery.manufacturer import Manufacturer as _Manufacturer

    created = manufacturer.pk is None
    old_active = False
    if not created:
        try:
            old_active = _Manufacturer.objects.get(pk=manufacturer.pk).is_active
        except _Manufacturer.DoesNotExist:
            pass

    super(_Manufacturer, manufacturer).save(*args, **kwargs)
    handle_manufacturer_save(manufacturer=manufacturer, created=created, old_active=old_active)


def delete_manufacturer(manufacturer, *args, **kwargs):
    """Delete Manufacturer and perform side-effects.

    Calls the base delete, then performs audit logging.
    """
    from micboard.models.discovery.manufacturer import Manufacturer as _Manufacturer

    result = super(_Manufacturer, manufacturer).delete(*args, **kwargs)
    handle_manufacturer_delete(manufacturer=manufacturer)
    return result


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
