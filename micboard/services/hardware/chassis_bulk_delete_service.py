"""Authorized bulk deletion of wireless chassis."""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied
from django.db import transaction

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.hardware.dtos import ChassisBulkDeleteResult
from micboard.services.shared.access_policy import tenant_role_access

logger = logging.getLogger(__name__)


class ChassisBulkDeleteService:
    """Delete a caller-selected set of chassis in one authorized, reconciled pass."""

    @classmethod
    def delete(
        cls,
        *,
        chassis_ids: list[int],
        requested_by: Any,
        using: str = "default",
    ) -> ChassisBulkDeleteResult:
        """Delete every selected chassis, replacing per-row cleanup with one reconciliation.

        Authorization runs before any side effect: a selection the caller may not delete in
        full is rejected without locking rows, scheduling discovery, or deleting anything.

        Raises:
            PermissionDenied: If any selected chassis is outside the caller's manageable
                scope, including rows that no longer exist.
        """
        selected_ids = sorted(set(chassis_ids))
        if not selected_ids:
            return ChassisBulkDeleteResult(deleted_count=0)

        cls._authorize(selected_ids=selected_ids, requested_by=requested_by, using=using)

        from micboard.model_lifecycle import suppress_chassis_delete_hooks
        from micboard.services.core.hardware_post_save_hooks import HardwarePostSaveHooks

        with transaction.atomic(using=using):
            locked = list(
                WirelessChassis._default_manager.using(using)
                .select_for_update()
                .filter(pk__in=selected_ids)
                .order_by("pk")
            )
            # The first check ran before these rows were locked, so a concurrent location
            # change could have moved one out of scope in between. Re-check against the
            # locked rows, and delete those, not the identifiers the caller supplied.
            locked_ids = [chassis.pk for chassis in locked]
            cls._authorize(
                selected_ids=locked_ids,
                requested_by=requested_by,
                using=using,
            )
            if len(locked_ids) != len(selected_ids):
                raise PermissionDenied

            HardwarePostSaveHooks.handle_chassis_bulk_delete(
                chassis_list=locked,
                using=using,
            )
            with suppress_chassis_delete_hooks():
                WirelessChassis._default_manager.using(using).filter(pk__in=locked_ids).delete()

        reconciled = sorted(
            {chassis.manufacturer_id for chassis in locked if chassis.manufacturer_id is not None}
        )
        logger.info(
            "Deleted %d chassis and reconciled %d manufacturer(s)",
            len(locked),
            len(reconciled),
        )
        return ChassisBulkDeleteResult(
            deleted_count=len(locked),
            reconciled_manufacturer_ids=reconciled,
        )

    @classmethod
    def _authorize(
        cls,
        *,
        selected_ids: list[int],
        requested_by: Any,
        using: str,
    ) -> None:
        """Reject the whole selection unless every row is manageable by the caller."""
        if (
            requested_by is None
            or not getattr(requested_by, "is_active", False)
            or not getattr(requested_by, "is_staff", False)
            or not requested_by.has_perm("micboard.delete_wirelesschassis")
            or not tenant_role_access.can_manage_model(user=requested_by, model=WirelessChassis)
        ):
            raise PermissionDenied

        manageable = tenant_role_access.scope_manageable_queryset(
            WirelessChassis._default_manager.using(using).filter(pk__in=selected_ids),
            user=requested_by,
        )
        if manageable.count() != len(selected_ids):
            raise PermissionDenied
