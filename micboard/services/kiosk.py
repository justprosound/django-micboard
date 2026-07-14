"""Kiosk service layer for composing display wall data.

Aggregates hardware, monitoring, and assignment data into optimized
structures for HTMX partials used in kiosk and dashboard views.
"""

from __future__ import annotations

import logging
from typing import Any

from micboard.models.hardware.charger import Charger
from micboard.models.monitoring.performer_assignment import PerformerAssignment

logger = logging.getLogger(__name__)


class KioskService:
    """Business logic for kiosk and dashboard display aggregation."""

    @staticmethod
    def get_dashboard_summary() -> dict[str, Any]:
        """Get high-level summary stats for main dashboard."""
        from micboard.models.hardware.wireless_chassis import WirelessChassis
        from micboard.models.hardware.wireless_unit import WirelessUnit
        from micboard.models.monitoring.alert import Alert

        return {
            "online_chassis": WirelessChassis.objects.filter(is_online=True).count(),
            "online_units": WirelessUnit.objects.filter(status="online").count(),
            "active_alerts": Alert.objects.filter(status="pending").count(),
        }

    @staticmethod
    def get_charger_dashboard_data(*, user) -> dict[str, Any]:
        """Compose optimized data for the charger dashboard grid."""
        chargers = (
            Charger.objects.for_user(user=user)
            .filter(is_active=True)
            .prefetch_related("slots")
            .order_by("order", "name")
        )

        # Map serials to performers
        serial_to_performer = {}
        assignments = (
            PerformerAssignment.objects.for_user(user=user)
            .filter(is_active=True)
            .select_related("performer", "wireless_unit")
        )

        for assignment in assignments:
            unit = assignment.wireless_unit
            if unit and unit.serial_number:
                serial_to_performer[unit.serial_number] = {
                    "name": assignment.performer.name,
                    "title": assignment.performer.title or "",
                    "photo_url": assignment.performer.photo.url
                    if assignment.performer.photo
                    else None,
                }

        return {
            "chargers": chargers,
            "serial_to_performer": serial_to_performer,
        }

    @staticmethod
    def get_section_data(*, section_id: int, user) -> dict[str, Any]:
        """Return performer data for one display-wall section."""
        from micboard.services.core.charger_assignment import ChargerAssignmentService

        return {
            "performers": ChargerAssignmentService.get_wall_section_performers(
                section_id,
                user=user,
            )
        }
