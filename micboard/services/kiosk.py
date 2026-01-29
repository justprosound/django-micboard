"""Kiosk service layer for composing display wall data.

Aggregates hardware, monitoring, and assignment data into optimized
structures for HTMX partials used in kiosk and dashboard views.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models import Prefetch

from micboard.models import Charger, PerformerAssignment

logger = logging.getLogger(__name__)


class KioskService:
    """Business logic for kiosk and dashboard display aggregation."""

    @staticmethod
    def get_dashboard_summary() -> dict[str, Any]:
        """Get high-level summary stats for main dashboard."""
        from micboard.models import Alert, WirelessChassis, WirelessUnit

        return {
            "online_chassis": WirelessChassis.objects.filter(is_online=True).count(),
            "online_units": WirelessUnit.objects.filter(status="online").count(),
            "active_alerts": Alert.objects.filter(status="pending").count(),
        }

    @staticmethod
    def get_charger_dashboard_data() -> dict[str, Any]:
        """Compose optimized data for the charger dashboard grid."""
        # Get active chargers with their slots
        chargers = (
            Charger.objects.filter(is_active=True)
            .prefetch_related(
                Prefetch(
                    "slots", queryset=Charger.objects.none().slots.all().order_by("slot_number")
                )  # Fix: need proper queryset
            )
            .order_by("order", "name")
        )

        # Real logic for slots sorting
        chargers = (
            Charger.objects.filter(is_active=True)
            .prefetch_related("slots")
            .order_by("order", "name")
        )

        # Map serials to performers
        serial_to_performer = {}
        assignments = PerformerAssignment.objects.filter(is_active=True).select_related(
            "performer", "wireless_unit"
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
