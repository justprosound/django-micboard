"""Service layer for charger assignments and performer-to-device mapping."""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import Prefetch

from micboard.models.hardware.charger import ChargerSlot
from micboard.models.hardware.wireless_unit import WirelessUnit
from micboard.models.monitoring.performer_assignment import PerformerAssignment
from micboard.services.hardware.wireless_unit_service import get_battery_percentage

logger = logging.getLogger(__name__)


class ChargerAssignmentService:
    """Service for managing charger slot assignments and performer lookups."""

    @staticmethod
    def _serialize_performer_for_slot(
        slot: ChargerSlot,
        unit: WirelessUnit,
        assignment: PerformerAssignment,
    ) -> dict[str, Any]:
        """Serialize an already-loaded slot, unit, and performer assignment."""
        channel_info = None
        if unit.assigned_resource:
            channel_info = {
                "frequency": unit.assigned_resource.frequency,
                "channel_number": unit.assigned_resource.channel_number,
                "rf_signal_strength": unit.assigned_resource.rf_signal_strength,
                "audio_level": unit.assigned_resource.audio_level,
                "link_direction": unit.assigned_resource.link_direction,
            }

        return {
            "performer_id": assignment.performer.id,
            "performer_name": assignment.performer.name,
            "performer_title": assignment.performer.title,
            "performer_photo": (
                assignment.performer.photo.url if assignment.performer.photo else None
            ),
            "unit_id": unit.id,
            "unit_type": unit.device_type,
            "unit_battery": unit.battery,
            "unit_battery_percent": get_battery_percentage(unit),
            "unit_status": unit.status,
            "unit_rf_level": unit.rf_level,
            "unit_audio_level": unit.audio_level,
            "channel": channel_info,
            "assignment_priority": assignment.priority,
            "slot_number": slot.slot_number,
            "charger_id": slot.charger_id,
        }

    @staticmethod
    def get_performer_for_slot(slot: ChargerSlot, *, user) -> dict[str, Any] | None:
        """Get performer and assignment info for a charger slot.

        Returns performer metadata and RF channel assignment if device
        is docked and linked to a PerformerAssignment.

        Args:
            slot: ChargerSlot instance

        Returns:
            Dict with performer, unit, assignment, and channel info, or None
        """
        if not slot.occupied or not slot.device_serial:
            return None

        try:
            # Find wireless unit by serial number
            unit = (
                WirelessUnit.objects.for_user(user=user)
                .select_related(
                    "assigned_resource",
                    "base_chassis",
                    "base_chassis__location",
                )
                .get(serial_number=slot.device_serial)
            )

            # Find active performance assignment
            assignment = (
                PerformerAssignment.objects.for_user(user=user)
                .filter(
                    wireless_unit=unit,
                    is_active=True,
                )
                .select_related(
                    "performer",
                    "monitoring_group",
                    "wireless_unit",
                )
                .first()
            )

            if not assignment:
                return None

            return ChargerAssignmentService._serialize_performer_for_slot(
                slot,
                unit,
                assignment,
            )

        except WirelessUnit.DoesNotExist:
            logger.warning("WirelessUnit not found for serial %s", slot.device_serial)
            return None
        except Exception as e:
            logger.exception("Error getting performer for slot %s: %s", slot.id, e)
            return None

    @staticmethod
    def get_charger_performers(charger_id: int, *, user) -> list[dict[str, Any]]:
        """Get all performers on docked units in a charger.

        Args:
            charger_id: Charger model ID

        Returns:
            List of performer dicts with unit and channel info
        """
        from micboard.models.hardware.charger import Charger
        from micboard.services.monitoring.monitoring_access import MonitoringService

        try:
            charger = MonitoringService.get_accessible_chargers(user).get(id=charger_id)
        except Charger.DoesNotExist:
            return []

        performers = []
        for slot in charger.slots.filter(occupied=True):
            performer_info = ChargerAssignmentService.get_performer_for_slot(slot, user=user)
            if performer_info:
                performers.append(performer_info)

        return performers

    @staticmethod
    def get_wall_section_performers(section_id: int, *, user) -> list[dict[str, Any]]:
        """Get all performers on chargers assigned to a wall section.

        Args:
            section_id: WallSection model ID

        Returns:
            List of performer dicts organized by charger
        """
        from micboard.models.hardware.display_wall import WallSection
        from micboard.services.monitoring.monitoring_access import MonitoringService

        try:
            section = (
                MonitoringService.get_accessible_wall_sections(user)
                .prefetch_related("chargers")
                .get(id=section_id)
            )
        except WallSection.DoesNotExist:
            return []

        performers_by_charger = []
        accessible_chargers = MonitoringService.get_accessible_chargers(user)
        for charger in section.chargers.filter(is_active=True, pk__in=accessible_chargers):
            charger_performers = ChargerAssignmentService.get_charger_performers(
                charger.id,
                user=user,
            )
            if charger_performers:
                performers_by_charger.append(
                    {
                        "charger": {
                            "id": charger.id,
                            "name": charger.name,
                            "location_id": charger.location_id,
                        },
                        "performers": charger_performers,
                    }
                )

        return performers_by_charger

    @staticmethod
    def _get_units_by_serial(
        slots: list[ChargerSlot],
        *,
        user,
    ) -> dict[str, WirelessUnit | None]:
        """Bulk-load unique visible wireless units for occupied charger slots."""
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
        user,
    ) -> dict[int, PerformerAssignment]:
        """Bulk-load the first active visible assignment for each wireless unit."""
        unit_ids = [unit.id for unit in units_by_serial.values() if unit is not None]
        assignments_by_unit: dict[int, PerformerAssignment] = {}
        if not unit_ids:
            return assignments_by_unit

        assignments = (
            PerformerAssignment.objects.for_user(user=user)
            .filter(wireless_unit_id__in=unit_ids, is_active=True)
            .select_related("performer")
        )
        for assignment in assignments:
            assignments_by_unit.setdefault(assignment.wireless_unit_id, assignment)
        return assignments_by_unit

    @staticmethod
    def _serialize_wall_sections(
        sections: list[Any],
        units_by_serial: dict[str, WirelessUnit | None],
        assignments_by_unit: dict[int, PerformerAssignment],
    ) -> list[dict[str, Any]]:
        """Serialize prefetched wall sections without issuing ORM queries."""
        sections_data = []
        for section in sections:
            performers = []
            for charger in section.visible_chargers:
                charger_performers = []
                for slot in charger.occupied_slots:
                    unit = units_by_serial.get(slot.device_serial)
                    assignment = assignments_by_unit.get(unit.id) if unit else None
                    if unit and assignment:
                        charger_performers.append(
                            ChargerAssignmentService._serialize_performer_for_slot(
                                slot,
                                unit,
                                assignment,
                            )
                        )
                if charger_performers:
                    performers.append(
                        {
                            "charger": {
                                "id": charger.id,
                                "name": charger.name,
                                "location_id": charger.location_id,
                            },
                            "performers": charger_performers,
                        }
                    )
            sections_data.append(
                {
                    "section": {
                        "id": section.id,
                        "name": section.name,
                        "layout": section.layout,
                        "columns": section.columns,
                    },
                    "performers": performers,
                }
            )
        return sections_data

    @staticmethod
    def get_display_wall_data(wall_id: int, *, user) -> dict[str, Any]:
        """Get complete display data for a display wall.

        Gathers all performers and channel info for all sections
        of a display wall.

        Args:
            wall_id: DisplayWall model ID

        Returns:
            Dict with wall info and sections with performer data
        """
        from micboard.models.hardware.display_wall import DisplayWall, WallSection
        from micboard.services.monitoring.monitoring_access import MonitoringService

        visible_chargers = MonitoringService.get_accessible_chargers(user).filter(is_active=True)
        visible_chargers = visible_chargers.prefetch_related(
            Prefetch(
                "slots",
                queryset=ChargerSlot.objects.filter(occupied=True).order_by("slot_number"),
                to_attr="occupied_slots",
            )
        )
        active_sections = WallSection.objects.filter(is_active=True).order_by("display_order")
        active_sections = active_sections.prefetch_related(
            Prefetch(
                "chargers",
                queryset=visible_chargers,
                to_attr="visible_chargers",
            )
        )

        try:
            wall = (
                MonitoringService.get_accessible_display_walls(user)
                .prefetch_related(
                    Prefetch(
                        "sections",
                        queryset=active_sections,
                        to_attr="active_sections",
                    )
                )
                .get(id=wall_id)
            )
        except DisplayWall.DoesNotExist:
            return {}

        occupied_slots: list[ChargerSlot] = [
            slot
            for section in wall.active_sections
            for charger in section.visible_chargers
            for slot in charger.occupied_slots
        ]
        units_by_serial = ChargerAssignmentService._get_units_by_serial(
            occupied_slots,
            user=user,
        )
        assignments_by_unit = ChargerAssignmentService._get_assignments_by_unit(
            units_by_serial,
            user=user,
        )
        sections_data = ChargerAssignmentService._serialize_wall_sections(
            wall.active_sections,
            units_by_serial,
            assignments_by_unit,
        )

        return {
            "wall": {
                "id": wall.id,
                "name": wall.name,
                "kiosk_id": wall.kiosk_id,
                "display_width_px": wall.display_width_px,
                "display_height_px": wall.display_height_px,
                "orientation": wall.orientation,
                "refresh_interval_seconds": wall.refresh_interval_seconds,
                "show_performer_photos": wall.show_performer_photos,
                "show_rf_levels": wall.show_rf_levels,
                "show_battery_levels": wall.show_battery_levels,
                "show_audio_levels": wall.show_audio_levels,
            },
            "sections": sections_data,
        }

    @staticmethod
    def assign_charger_to_section(charger_id: int, section_id: int) -> bool:
        """Assign a charger to a wall section.

        Args:
            charger_id: Charger model ID
            section_id: WallSection model ID

        Returns:
            True if successful, False otherwise
        """
        from micboard.models.hardware.charger import Charger
        from micboard.models.hardware.display_wall import WallSection

        try:
            charger = Charger.objects.get(id=charger_id)
            section = WallSection.objects.get(id=section_id)
            section.chargers.add(charger)
            logger.info("Assigned charger %s to section %s", charger_id, section_id)
            return True
        except (Charger.DoesNotExist, WallSection.DoesNotExist) as e:
            logger.warning("Error assigning charger to section: %s", e)
            return False

    @staticmethod
    def remove_charger_from_section(charger_id: int, section_id: int) -> bool:
        """Remove a charger from a wall section.

        Args:
            charger_id: Charger model ID
            section_id: WallSection model ID

        Returns:
            True if successful, False otherwise
        """
        from micboard.models.hardware.display_wall import WallSection

        try:
            section = WallSection.objects.get(id=section_id)
            section.chargers.remove(charger_id)
            logger.info("Removed charger %s from section %s", charger_id, section_id)
            return True
        except WallSection.DoesNotExist:
            logger.warning("Section %s not found", section_id)
            return False
