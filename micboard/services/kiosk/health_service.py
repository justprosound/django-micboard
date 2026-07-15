"""Bounded, tenant-scoped health projections for display walls."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from django.db.models import Prefetch
from django.utils import timezone

from micboard.models.hardware.charger import Charger, ChargerSlot
from micboard.models.hardware.display_wall import DisplayWall, WallSection
from micboard.services.kiosk.dtos import (
    MAX_KIOSK_CHARGERS_PER_SECTION,
    MAX_KIOSK_SECTIONS,
    MAX_KIOSK_SLOTS_PER_CHARGER,
    DisplayWallHealthSnapshot,
    KioskChargerHealthSnapshot,
    KioskHealthChargerMetadata,
    KioskSlotHealthSnapshot,
)
from micboard.services.monitoring.monitoring_access import MonitoringService


class KioskHealthService:
    """Build bounded charger-health snapshots inside the caller's tenant scope."""

    HEARTBEAT_TIMEOUT_SECONDS = 120

    @classmethod
    def get_wall_health(
        cls,
        *,
        wall_id: int,
        user: Any,
    ) -> DisplayWallHealthSnapshot | None:
        """Return one accessible wall's health without materializing unbounded inventory."""
        slots = ChargerSlot.objects.order_by("slot_number", "pk")[: MAX_KIOSK_SLOTS_PER_CHARGER + 1]
        chargers = (
            MonitoringService.get_accessible_chargers(user)
            .filter(is_active=True)
            .prefetch_related(Prefetch("slots", queryset=slots, to_attr="health_slots"))
            .order_by("pk")[: MAX_KIOSK_CHARGERS_PER_SECTION + 1]
        )
        sections = (
            WallSection.objects.filter(is_active=True)
            .prefetch_related(
                Prefetch("chargers", queryset=chargers, to_attr="accessible_chargers")
            )
            .order_by("display_order", "pk")[: MAX_KIOSK_SECTIONS + 1]
        )
        try:
            wall = (
                MonitoringService.get_accessible_display_walls(user)
                .filter(is_active=True)
                .prefetch_related(
                    Prefetch("sections", queryset=sections, to_attr="active_sections")
                )
                .get(pk=wall_id)
            )
        except DisplayWall.DoesNotExist:
            return None

        sections_truncated = len(wall.active_sections) > MAX_KIOSK_SECTIONS
        chargers_truncated = False
        slots_truncated = False
        seen_charger_ids: set[int] = set()
        charger_health: list[KioskChargerHealthSnapshot] = []
        now = timezone.now()

        for section in wall.active_sections[:MAX_KIOSK_SECTIONS]:
            chargers_truncated |= len(section.accessible_chargers) > MAX_KIOSK_CHARGERS_PER_SECTION
            for charger in section.accessible_chargers[:MAX_KIOSK_CHARGERS_PER_SECTION]:
                if charger.pk in seen_charger_ids:
                    continue
                seen_charger_ids.add(charger.pk)
                snapshot = cls._build_charger_health(charger, now=now)
                slots_truncated |= snapshot.slots_truncated
                charger_health.append(snapshot)

        return DisplayWallHealthSnapshot(
            wall_id=wall.pk,
            chargers=charger_health,
            sections_truncated=sections_truncated,
            chargers_truncated=chargers_truncated,
            slots_truncated=slots_truncated,
            section_limit=MAX_KIOSK_SECTIONS,
            charger_limit=MAX_KIOSK_SECTIONS * MAX_KIOSK_CHARGERS_PER_SECTION,
            slot_limit=MAX_KIOSK_SLOTS_PER_CHARGER,
        )

    @classmethod
    def _build_charger_health(
        cls,
        charger: Charger,
        *,
        now: datetime,
    ) -> KioskChargerHealthSnapshot:
        """Build one charger result from its sentinel-bounded prefetched slots."""
        heartbeat_age_seconds = (
            int((now - charger.last_seen).total_seconds()) if charger.last_seen else None
        )
        charger_connected = (
            heartbeat_age_seconds is not None
            and heartbeat_age_seconds <= cls.HEARTBEAT_TIMEOUT_SECONDS
        )
        loaded_slots: list[ChargerSlot] = cast(Any, charger).health_slots
        slots_truncated = len(loaded_slots) > MAX_KIOSK_SLOTS_PER_CHARGER
        slots = [
            cls._check_slot(slot, now=now) for slot in loaded_slots[:MAX_KIOSK_SLOTS_PER_CHARGER]
        ]
        occupied_count = sum(slot.occupied for slot in slots)
        connected_count = sum(slot.connected for slot in slots if slot.occupied)
        issue_count = sum(len(slot.issues) for slot in slots if slot.occupied)

        if not charger_connected:
            health = "offline"
        elif issue_count:
            health = "degraded"
        elif not occupied_count:
            health = "idle"
        else:
            health = "healthy"

        return KioskChargerHealthSnapshot(
            charger=KioskHealthChargerMetadata(
                id=charger.pk,
                name=charger.name,
                status=charger.status,
                ip=str(charger.ip) if charger.ip else None,
            ),
            health=health,
            connected=charger_connected,
            last_heartbeat_seconds_ago=heartbeat_age_seconds,
            occupied_slots=occupied_count,
            connected_slots=connected_count,
            total_slots=charger.slot_count,
            issue_count=issue_count,
            slots=slots,
            slots_truncated=slots_truncated,
            slot_limit=MAX_KIOSK_SLOTS_PER_CHARGER,
        )

    @classmethod
    def _check_slot(
        cls,
        slot: ChargerSlot,
        *,
        now: datetime,
    ) -> KioskSlotHealthSnapshot:
        """Assess one prefetched slot without further database queries."""
        issues: list[str] = []
        result = KioskSlotHealthSnapshot(
            slot_id=slot.pk,
            slot_number=slot.slot_number,
            charger_id=slot.charger_id,
            occupied=slot.occupied,
            issues=issues,
        )
        if not slot.occupied:
            result.issues.append("Slot not marked as occupied")
            return result
        if not slot.device_serial:
            result.issues.append("No device serial number")
            return result
        if slot.device_status and slot.device_status.lower() in {"error", "offline", "fault"}:
            result.issues.append(f"Device status is {slot.device_status}")
            return result
        if slot.battery_percent is not None and slot.battery_percent < 5:
            result.issues.append(f"Battery critically low: {slot.battery_percent}%")
        if not slot.charger.last_seen:
            result.issues.append("Charger has never reported a heartbeat")
            return result

        age_seconds = (now - slot.charger.last_seen).total_seconds()
        if age_seconds > cls.HEARTBEAT_TIMEOUT_SECONDS:
            result.issues.append(
                f"Charger not seen for {age_seconds:.0f}s "
                f"(timeout: {cls.HEARTBEAT_TIMEOUT_SECONDS}s)"
            )
            return result

        result.connected = True
        result.is_valid = not result.issues
        return result
