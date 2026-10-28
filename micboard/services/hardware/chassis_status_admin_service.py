"""Operator-driven chassis online/offline changes through the status lifecycle."""

from django.db.models import QuerySet

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.core.hardware_lifecycle import HardwareLifecycleManager
from micboard.services.hardware.chassis_admin_dtos import (
    ChassisStatusChangeResult,
    RefusedChassisStatusChange,
)


class ChassisStatusAdminService:
    """Apply a bulk online/offline request one chassis at a time."""

    @staticmethod
    def set_online(
        *,
        queryset: QuerySet[WirelessChassis],
        online: bool,
    ) -> ChassisStatusChangeResult:
        """Move each selected chassis, reporting those the status graph refuses."""
        lifecycle = HardwareLifecycleManager()
        move = lifecycle.mark_online if online else lifecycle.mark_offline
        updated = 0
        refused: list[RefusedChassisStatusChange] = []
        for chassis in queryset.order_by("pk"):
            if move(chassis):
                updated += 1
            else:
                refused.append(
                    RefusedChassisStatusChange(
                        id=chassis.pk,
                        name=chassis.name,
                        status=chassis.status,
                    )
                )
        return ChassisStatusChangeResult(updated=updated, refused=refused)
