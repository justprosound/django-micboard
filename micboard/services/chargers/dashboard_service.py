"""Tenant-scoped charger-dashboard projection service."""

from __future__ import annotations

from typing import Any, cast

from django.db.models import Prefetch

from micboard.models.hardware.charger import Charger, ChargerSlot
from micboard.services.chargers.dashboard_dtos import (
    MAX_DASHBOARD_CHARGERS,
    MAX_DASHBOARD_SLOTS_PER_CHARGER,
    ChargerDashboardChargerSnapshot,
    ChargerDashboardPerformerSnapshot,
    ChargerDashboardSlotSnapshot,
    ChargerDashboardSnapshot,
)
from micboard.services.core.performer_assignment import PerformerAssignmentService


class ChargerDashboardService:
    """Own charger-grid loading and performer identity mapping."""

    @staticmethod
    def _get_chargers(*, user: Any) -> tuple[list[Charger], bool]:
        """Load a bounded visible charger prefix and detect overflow."""
        slots = ChargerSlot.objects.order_by("slot_number", "pk")[
            : MAX_DASHBOARD_SLOTS_PER_CHARGER + 1
        ]
        chargers = cast(
            list[Charger],
            list(
                Charger.objects.for_user(user=user)
                .filter(is_active=True)
                .order_by("order", "name", "pk")[: MAX_DASHBOARD_CHARGERS + 1]
                .prefetch_related(
                    Prefetch(
                        "slots",
                        queryset=slots,
                        to_attr="_dashboard_slots",
                    )
                )
            ),
        )
        return chargers[:MAX_DASHBOARD_CHARGERS], len(chargers) > MAX_DASHBOARD_CHARGERS

    @staticmethod
    def _get_performers_by_serial(
        *,
        user: Any,
        occupied_serials: set[str],
    ) -> dict[str, ChargerDashboardPerformerSnapshot]:
        """Map only occupied visible units onto active performer assignments."""
        if not occupied_serials:
            return {}

        assignments = PerformerAssignmentService.get_preferred_active_assignments_for_serials(
            user=user,
            serial_numbers=occupied_serials,
        )
        performers: dict[str, ChargerDashboardPerformerSnapshot] = {}
        for assignment in assignments:
            unit = assignment.wireless_unit
            performer = assignment.performer
            performers[unit.serial_number] = ChargerDashboardPerformerSnapshot(
                name=performer.name,
                title=performer.title or "",
                photo_url=performer.photo.url if performer.photo else None,
            )
        return performers

    @staticmethod
    def _to_snapshot(
        *,
        charger: Charger,
        performers_by_serial: dict[str, ChargerDashboardPerformerSnapshot],
    ) -> ChargerDashboardChargerSnapshot:
        """Map one prefetched ORM graph to a primitive nested projection."""
        loaded_slots = list(getattr(charger, "_dashboard_slots", ()))
        slots = loaded_slots[:MAX_DASHBOARD_SLOTS_PER_CHARGER]
        return ChargerDashboardChargerSnapshot(
            id=charger.pk,
            name=charger.name,
            model_name=charger.model,
            ip_address=charger.ip,
            slots=[
                ChargerDashboardSlotSnapshot(
                    slot_number=slot.slot_number,
                    occupied=slot.occupied,
                    device_serial=slot.device_serial,
                    device_model=slot.device_model,
                    battery_percent=slot.battery_percent,
                    device_firmware_version=slot.device_firmware_version,
                    device_status=slot.device_status,
                    is_functional=slot.is_functional,
                    performer=(
                        performers_by_serial.get(slot.device_serial) if slot.occupied else None
                    ),
                )
                for slot in slots
            ],
            slots_truncated=len(loaded_slots) > MAX_DASHBOARD_SLOTS_PER_CHARGER,
            slot_limit=MAX_DASHBOARD_SLOTS_PER_CHARGER,
        )

    @classmethod
    def get_snapshot(cls, *, user: Any) -> ChargerDashboardSnapshot:
        """Return the complete charger-grid projection for one user."""
        chargers, chargers_truncated = cls._get_chargers(user=user)
        occupied_serials = {
            slot.device_serial
            for charger in chargers
            for slot in getattr(charger, "_dashboard_slots", ())
            if slot.occupied and slot.device_serial
        }
        performers_by_serial = cls._get_performers_by_serial(
            user=user,
            occupied_serials=occupied_serials,
        )
        return ChargerDashboardSnapshot(
            chargers=[
                cls._to_snapshot(
                    charger=charger,
                    performers_by_serial=performers_by_serial,
                )
                for charger in chargers
            ],
            chargers_truncated=chargers_truncated,
            charger_limit=MAX_DASHBOARD_CHARGERS,
        )
