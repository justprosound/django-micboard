"""Service layer for charger assignments and performer-to-device mapping."""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import Prefetch

from micboard.models import ChargerSlot, PerformerAssignment, WirelessUnit

logger = logging.getLogger(__name__)


class ChargerAssignmentService:
    """Service for managing charger slot assignments and performer lookups."""

    @staticmethod
    def get_performer_for_slot(slot: ChargerSlot) -> dict[str, Any] | None:
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
            unit = WirelessUnit.objects.select_related(
                "base_chassis",
                "base_chassis__location",
            ).get(serial_number=slot.device_serial)

            # Find active performance assignment
            assignment = (
                PerformerAssignment.objects.filter(
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

            # Get RF channel if unit is active on one
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
                "unit_type": unit.unit_type,
                "unit_battery": unit.battery,
                "unit_battery_percent": unit.battery_percentage,
                "unit_status": unit.status,
                "unit_rf_level": unit.rf_level,
                "unit_audio_level": unit.audio_level,
                "channel": channel_info,
                "assignment_priority": assignment.priority,
                "slot_number": slot.slot_number,
                "charger_id": slot.charger_id,
            }

        except WirelessUnit.DoesNotExist:
            logger.warning(f"WirelessUnit not found for serial {slot.device_serial}")
            return None
        except Exception as e:
            logger.exception(f"Error getting performer for slot {slot.id}: {e}")
            return None

    @staticmethod
    def get_charger_performers(charger_id: int) -> list[dict[str, Any]]:
        """Get all performers on docked units in a charger.

        Args:
            charger_id: Charger model ID

        Returns:
            List of performer dicts with unit and channel info
        """
        from micboard.models import Charger

        try:
            charger = Charger.objects.get(id=charger_id)
        except Charger.DoesNotExist:
            return []

        performers = []
        for slot in charger.slots.filter(occupied=True):
            performer_info = ChargerAssignmentService.get_performer_for_slot(slot)
            if performer_info:
                performers.append(performer_info)

        return performers

    @staticmethod
    def get_wall_section_performers(section_id: int) -> list[dict[str, Any]]:
        """Get all performers on chargers assigned to a wall section.

        Args:
            section_id: WallSection model ID

        Returns:
            List of performer dicts organized by charger
        """
        from micboard.models import WallSection

        try:
            section = WallSection.objects.prefetch_related("chargers").get(id=section_id)
        except WallSection.DoesNotExist:
            return []

        performers_by_charger = []
        for charger in section.chargers.filter(is_active=True):
            charger_performers = ChargerAssignmentService.get_charger_performers(charger.id)
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
    def get_display_wall_data(wall_id: int) -> dict[str, Any]:
        """Get complete display data for a display wall.

        Gathers all performers and channel info for all sections
        of a display wall.

        Args:
            wall_id: DisplayWall model ID

        Returns:
            Dict with wall info and sections with performer data
        """
        from micboard.models import DisplayWall

        try:
            wall = DisplayWall.objects.prefetch_related(
                Prefetch(
                    "sections",
                    queryset=Prefetch(
                        "chargers",
                        queryset=Prefetch(
                            "slots",
                        ),
                    ),
                ),
            ).get(id=wall_id)
        except DisplayWall.DoesNotExist:
            return {}

        sections_data = []
        for section in wall.sections.filter(is_active=True):
            performers = ChargerAssignmentService.get_wall_section_performers(section.id)
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
        from micboard.models import Charger, WallSection

        try:
            charger = Charger.objects.get(id=charger_id)
            section = WallSection.objects.get(id=section_id)
            section.chargers.add(charger)
            logger.info(f"Assigned charger {charger_id} to section {section_id}")
            return True
        except (Charger.DoesNotExist, WallSection.DoesNotExist) as e:
            logger.warning(f"Error assigning charger to section: {e}")
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
        from micboard.models import WallSection

        try:
            section = WallSection.objects.get(id=section_id)
            section.chargers.remove(charger_id)
            logger.info(f"Removed charger {charger_id} from section {section_id}")
            return True
        except WallSection.DoesNotExist:
            logger.warning(f"Section {section_id} not found")
            return False
