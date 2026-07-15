"""Wireless chassis save lifecycle and committed status side effects."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from micboard.services.hardware.chassis_regulatory_service import (
    prepare_chassis_regulatory_fields,
)
from micboard.services.hardware.dtos import ChassisSaveContext

if TYPE_CHECKING:
    from micboard.models.hardware.wireless_chassis import WirelessChassis

_OPERATIONAL_STATES: set[str] = {"online", "degraded"}
_VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "discovered": {"provisioning", "offline", "retired"},
    "provisioning": {"online", "offline", "discovered"},
    "online": {"degraded", "offline", "maintenance"},
    "degraded": {"online", "offline", "maintenance"},
    "offline": {"online", "degraded", "maintenance", "retired"},
    "maintenance": {"online", "offline", "retired"},
    "retired": set(),
}


def prepare_chassis_for_save(
    chassis: WirelessChassis,
    *,
    using: str = "default",
) -> ChassisSaveContext:
    """Validate lifecycle state and enrich regulatory fields before persistence."""
    created = chassis._state.adding
    old_status, lifecycle_update_fields = _prepare_lifecycle_fields(
        chassis,
        created=created,
        using=using,
    )
    prepare_chassis_regulatory_fields(chassis)
    return ChassisSaveContext(
        created=created,
        old_status=old_status,
        status_changed=old_status is not None and old_status != chassis.status,
        update_fields=lifecycle_update_fields,
    )


def finalize_chassis_save(
    chassis: WirelessChassis,
    context: ChassisSaveContext,
    *,
    using: str = "default",
) -> None:
    """Emit audit and realtime effects after a persisted status change."""
    if not context.status_changed:
        return

    old_status = context.old_status
    from micboard.services.maintenance.audit import AuditService

    AuditService.log_activity(
        activity_type="hardware",
        operation="status_change",
        summary=f"Chassis status changed: {old_status} → {chassis.status}",
        obj=chassis,
        old_values={"status": old_status},
        new_values={"status": chassis.status},
        using=using,
    )
    _schedule_status_broadcast(chassis, using=using)


def _prepare_lifecycle_fields(
    chassis: WirelessChassis,
    *,
    created: bool,
    using: str,
) -> tuple[str | None, set[str]]:
    old_status: str | None = None
    lifecycle_update_fields: set[str] = set()
    if created:
        if chassis.status in _OPERATIONAL_STATES:
            chassis.is_online = True
            chassis.last_online_at = timezone.now()
            lifecycle_update_fields.update({"is_online", "last_online_at"})
        return old_status, lifecycle_update_fields

    previous = (
        type(chassis)
        .objects.using(using)
        .only("status", "is_online", "last_online_at", "total_uptime_minutes")
        .get(pk=chassis.pk)
    )
    old_status = previous.status
    if old_status == chassis.status:
        return old_status, lifecycle_update_fields

    allowed = _VALID_STATUS_TRANSITIONS.get(old_status, set())
    if chassis.status not in allowed:
        allowed_label = ", ".join(sorted(allowed)) if allowed else "none (terminal state)"
        raise ValueError(
            f"Invalid status transition: {old_status} → {chassis.status}. Allowed: {allowed_label}"
        )

    now = timezone.now()
    was_operational = previous.is_online or old_status in _OPERATIONAL_STATES
    is_operational = chassis.status in _OPERATIONAL_STATES
    chassis.is_online = is_operational
    lifecycle_update_fields.add("is_online")
    if is_operational and not was_operational:
        chassis.last_online_at = now
        lifecycle_update_fields.add("last_online_at")
    elif not is_operational and was_operational:
        chassis.last_offline_at = now
        lifecycle_update_fields.add("last_offline_at")
        if previous.last_online_at:
            elapsed_minutes = max(
                0,
                int((now - previous.last_online_at).total_seconds() // 60),
            )
            chassis.total_uptime_minutes = previous.total_uptime_minutes + elapsed_minutes
            lifecycle_update_fields.add("total_uptime_minutes")
    return old_status, lifecycle_update_fields


def _broadcast_persisted_chassis_status(*, chassis_id: int, using: str) -> None:
    """Broadcast the final committed state, or no-op if the row was deleted."""
    from micboard.models.hardware.wireless_chassis import WirelessChassis

    try:
        chassis = (
            WirelessChassis._default_manager.using(using)
            .select_related("manufacturer")
            .get(pk=chassis_id)
        )
    except WirelessChassis.DoesNotExist:
        return

    from micboard.services.notification.broadcast_service import BroadcastService

    BroadcastService.broadcast_device_status(
        service_code=chassis.manufacturer.code,
        device_id=chassis.pk,
        device_type=type(chassis).__name__,
        status=chassis.status,
        is_active=chassis.is_online,
    )


def _schedule_status_broadcast(chassis: WirelessChassis, *, using: str) -> None:
    """Register at most one final-state broadcast per chassis and transaction."""
    connection = transaction.get_connection(using)
    marker = chassis.pk
    if any(
        getattr(callback, "_micboard_chassis_status_id", None) == marker
        for _savepoints, callback, _robust in connection.run_on_commit
    ):
        return
    callback = partial(
        _broadcast_persisted_chassis_status,
        chassis_id=chassis.pk,
        using=using,
    )
    callback._micboard_chassis_status_id = marker  # type: ignore[attr-defined]
    transaction.on_commit(callback, using=using, robust=True)
