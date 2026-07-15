"""Tenant-scoped projections for kiosk and charger-dashboard adapters."""

from __future__ import annotations

from typing import Any, cast

from django.db.models import Prefetch, QuerySet
from django.utils import timezone

from micboard.models.hardware.charger import Charger, ChargerSlot
from micboard.models.hardware.display_wall import DisplayWall, WallSection
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.core.performer_assignment import PerformerAssignmentService
from micboard.services.hardware.wireless_unit_service import get_battery_percentage
from micboard.services.kiosk.dtos import (
    MAX_KIOSK_CHARGERS_PER_SECTION,
    MAX_KIOSK_OCCUPIED_SLOTS_PER_CHARGER,
    MAX_KIOSK_SECTIONS,
    DisplayWallMetadata,
    DisplayWallSnapshot,
    KioskChargerGroupSnapshot,
    KioskChargerSnapshot,
    KioskPerformerSnapshot,
    RFChannelSnapshot,
    WallSectionSnapshot,
)
from micboard.services.monitoring.monitoring_access import MonitoringService


class KioskService:
    """Build bounded display projections behind one tenant-scoped interface."""

    @staticmethod
    def _serialize_performer(
        slot: ChargerSlot,
        unit: WirelessUnit,
        assignment: PerformerAssignment,
    ) -> KioskPerformerSnapshot:
        """Serialize one already-loaded performer assignment."""
        channel = unit.assigned_resource
        channel_snapshot = None
        if channel is not None:
            channel_snapshot = RFChannelSnapshot(
                frequency=channel.frequency,
                channel_number=channel.channel_number,
                rf_signal_strength=channel.rf_signal_strength,
                audio_level=channel.audio_level,
                link_direction=channel.link_direction,
            )
        performer = assignment.performer
        return KioskPerformerSnapshot(
            performer_id=performer.id,
            performer_name=performer.name,
            performer_title=performer.title,
            performer_photo=performer.photo.url if performer.photo else None,
            unit_id=unit.id,
            unit_type=unit.device_type,
            unit_battery=unit.battery,
            unit_battery_percent=get_battery_percentage(unit),
            unit_status=unit.status,
            unit_rf_level=unit.rf_level,
            unit_audio_level=unit.audio_level,
            channel=channel_snapshot,
            assignment_priority=assignment.priority,
            slot_number=slot.slot_number,
            charger_id=slot.charger_id,
        )

    @staticmethod
    def _get_units_by_serial(
        slots: list[ChargerSlot],
        *,
        user: Any,
    ) -> dict[str, WirelessUnit | None]:
        """Bulk-load visible units while rejecting ambiguous serial numbers."""
        device_serials = {slot.device_serial for slot in slots if slot.device_serial}
        units_by_serial: dict[str, WirelessUnit | None] = {}
        if not device_serials:
            return units_by_serial
        units = (
            WirelessUnit.objects.for_user(user=user)
            .filter(serial_number__in=device_serials)
            .select_related("assigned_resource")
        )
        for unit in units:
            if unit.serial_number in units_by_serial:
                units_by_serial[unit.serial_number] = None
            else:
                units_by_serial[unit.serial_number] = unit
        return units_by_serial

    @staticmethod
    def _get_assignments_by_unit(
        units_by_serial: dict[str, WirelessUnit | None],
        *,
        user: Any,
    ) -> dict[int, PerformerAssignment]:
        """Bulk-load the highest-priority active assignment for each unit."""
        unit_ids = [unit.id for unit in units_by_serial.values() if unit is not None]
        assignments_by_unit: dict[int, PerformerAssignment] = {}
        if not unit_ids:
            return assignments_by_unit
        assignments = PerformerAssignmentService.get_preferred_active_assignments_for_units(
            user=user,
            unit_ids=unit_ids,
        )
        return {assignment.wireless_unit_id: assignment for assignment in assignments}

    @classmethod
    def _serialize_sections(
        cls,
        sections: list[Any],
        *,
        user: Any,
    ) -> list[WallSectionSnapshot]:
        """Serialize a prefetched section graph without per-row queries."""
        section_rows: list[tuple[Any, list[tuple[Charger, list[ChargerSlot], bool]], bool]] = []
        occupied_slots: list[ChargerSlot] = []
        for section in sections:
            loaded_chargers = list(section.visible_chargers)
            chargers_truncated = len(loaded_chargers) > MAX_KIOSK_CHARGERS_PER_SECTION
            charger_rows: list[tuple[Charger, list[ChargerSlot], bool]] = []
            for charger in loaded_chargers[:MAX_KIOSK_CHARGERS_PER_SECTION]:
                loaded_slots = list(charger.occupied_slots)
                slots_truncated = len(loaded_slots) > MAX_KIOSK_OCCUPIED_SLOTS_PER_CHARGER
                slots = loaded_slots[:MAX_KIOSK_OCCUPIED_SLOTS_PER_CHARGER]
                charger_rows.append((charger, slots, slots_truncated))
                occupied_slots.extend(slots)
            section_rows.append((section, charger_rows, chargers_truncated))

        units_by_serial = cls._get_units_by_serial(occupied_slots, user=user)
        assignments_by_unit = cls._get_assignments_by_unit(units_by_serial, user=user)
        section_snapshots: list[WallSectionSnapshot] = []
        for section, charger_rows, chargers_truncated in section_rows:
            charger_groups: list[KioskChargerGroupSnapshot] = []
            section_slots_truncated = False
            for charger, slots, slots_truncated in charger_rows:
                section_slots_truncated = section_slots_truncated or slots_truncated
                performers: list[KioskPerformerSnapshot] = []
                for slot in slots:
                    unit = units_by_serial.get(slot.device_serial)
                    assignment = assignments_by_unit.get(unit.id) if unit else None
                    if unit is not None and assignment is not None:
                        performers.append(cls._serialize_performer(slot, unit, assignment))
                if performers:
                    charger_groups.append(
                        KioskChargerGroupSnapshot(
                            charger=KioskChargerSnapshot(
                                id=charger.id,
                                name=charger.name,
                                location_id=charger.location_id,
                            ),
                            performers=performers,
                            occupied_slots_truncated=slots_truncated,
                            occupied_slot_limit=MAX_KIOSK_OCCUPIED_SLOTS_PER_CHARGER,
                        )
                    )
            section_snapshots.append(
                WallSectionSnapshot(
                    id=section.id,
                    name=section.name,
                    layout=section.layout,
                    columns=section.columns,
                    performers=charger_groups,
                    chargers_truncated=chargers_truncated,
                    charger_limit=MAX_KIOSK_CHARGERS_PER_SECTION,
                    occupied_slots_truncated=section_slots_truncated,
                    occupied_slot_limit=MAX_KIOSK_OCCUPIED_SLOTS_PER_CHARGER,
                )
            )
        return section_snapshots

    @staticmethod
    def _visible_chargers(*, user: Any) -> QuerySet[Charger]:
        """Return active visible chargers with occupied slots prefetched."""
        occupied_slots = ChargerSlot.objects.filter(occupied=True).order_by(
            "slot_number",
            "pk",
        )[: MAX_KIOSK_OCCUPIED_SLOTS_PER_CHARGER + 1]
        return (
            MonitoringService.get_accessible_chargers(user)
            .filter(is_active=True)
            .order_by("order", "name", "pk")
            .prefetch_related(
                Prefetch(
                    "slots",
                    queryset=occupied_slots,
                    to_attr="occupied_slots",
                )
            )
        )

    @classmethod
    def _wall_queryset(cls, *, user: Any) -> QuerySet[DisplayWall]:
        """Return visible active walls with the full bounded graph prefetched."""
        visible_chargers = cls._visible_chargers(user=user)[: MAX_KIOSK_CHARGERS_PER_SECTION + 1]
        active_sections = WallSection.objects.filter(is_active=True).order_by(
            "display_order",
            "pk",
        )[: MAX_KIOSK_SECTIONS + 1]
        active_sections = active_sections.prefetch_related(
            Prefetch(
                "chargers",
                queryset=visible_chargers,
                to_attr="visible_chargers",
            )
        )
        return (
            MonitoringService.get_accessible_display_walls(user)
            .filter(is_active=True)
            .prefetch_related(
                Prefetch(
                    "sections",
                    queryset=active_sections,
                    to_attr="active_sections",
                )
            )
        )

    @classmethod
    def _snapshot_for(cls, *, user: Any, **lookup: Any) -> DisplayWallSnapshot | None:
        """Build a typed snapshot for one visible active wall lookup."""
        try:
            wall = cls._wall_queryset(user=user).get(**lookup)
        except DisplayWall.DoesNotExist:
            return None
        prefetched_wall = cast(Any, wall)
        loaded_sections: list[Any] = prefetched_wall.active_sections
        active_sections = loaded_sections[:MAX_KIOSK_SECTIONS]
        return DisplayWallSnapshot(
            wall=DisplayWallMetadata(
                id=wall.id,
                name=wall.name,
                kiosk_id=wall.kiosk_id,
                display_width_px=wall.display_width_px,
                display_height_px=wall.display_height_px,
                orientation=wall.orientation,
                refresh_interval_seconds=max(
                    DisplayWall.MIN_REFRESH_INTERVAL_SECONDS,
                    min(
                        wall.refresh_interval_seconds,
                        DisplayWall.MAX_REFRESH_INTERVAL_SECONDS,
                    ),
                ),
                show_performer_photos=wall.show_performer_photos,
                show_rf_levels=wall.show_rf_levels,
                show_battery_levels=wall.show_battery_levels,
                show_audio_levels=wall.show_audio_levels,
            ),
            sections=cls._serialize_sections(active_sections, user=user),
            sections_truncated=len(loaded_sections) > MAX_KIOSK_SECTIONS,
            section_limit=MAX_KIOSK_SECTIONS,
        )

    @classmethod
    def get_wall_snapshot(cls, wall_id: int, *, user: Any) -> DisplayWallSnapshot | None:
        """Return one visible active wall by database identifier."""
        return cls._snapshot_for(user=user, id=wall_id)

    @classmethod
    def get_kiosk_snapshot(cls, kiosk_id: str, *, user: Any) -> DisplayWallSnapshot | None:
        """Return one visible active wall by stable kiosk identifier."""
        return cls._snapshot_for(user=user, kiosk_id=kiosk_id)

    @classmethod
    def get_section_snapshot(cls, section_id: int, *, user: Any) -> WallSectionSnapshot | None:
        """Return one visible active section through the same bulk projection."""
        sections = MonitoringService.get_accessible_wall_sections(user).filter(is_active=True)
        visible_chargers = cls._visible_chargers(user=user)[: MAX_KIOSK_CHARGERS_PER_SECTION + 1]
        sections = sections.prefetch_related(
            Prefetch(
                "chargers",
                queryset=visible_chargers,
                to_attr="visible_chargers",
            )
        )
        try:
            section = sections.get(id=section_id)
        except WallSection.DoesNotExist:
            return None
        return cls._serialize_sections([section], user=user)[0]

    @staticmethod
    def record_heartbeat(kiosk_id: str, *, user: Any) -> bool:
        """Record activity only for a visible active kiosk."""
        updated = (
            MonitoringService.get_accessible_display_walls(user)
            .filter(kiosk_id=kiosk_id, is_active=True)
            .update(last_heartbeat=timezone.now())
        )
        return bool(updated)
