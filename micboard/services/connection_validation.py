"""Service for validating device connections and charger slot occupancy."""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from micboard.models import Charger, ChargerSlot

logger = logging.getLogger(__name__)


class ConnectionValidationService:
    """Service for checking charger slot connections and device validity."""

    HEARTBEAT_TIMEOUT_SECONDS = 120

    @staticmethod
    def check_slot_connection(slot: ChargerSlot) -> dict[str, Any]:
        """Check if a charger slot has a valid device connection.

        Validates:
        - Slot is marked as occupied
        - Device serial is present
        - Device status is not error/offline
        - Last seen is recent

        Args:
            slot: ChargerSlot instance

        Returns:
            Dict with connection status and details
        """
        result = {
            "slot_id": slot.id,
            "slot_number": slot.slot_number,
            "charger_id": slot.charger_id,
            "occupied": slot.occupied,
            "connected": False,
            "is_valid": False,
            "issues": [],
        }

        # Check if occupied
        if not slot.occupied:
            result["connected"] = False
            result["issues"].append("Slot not marked as occupied")
            return result

        # Check if device serial present
        if not slot.device_serial:
            result["connected"] = False
            result["issues"].append("No device serial number")
            return result

        # Check device status
        if slot.device_status and slot.device_status.lower() in ("error", "offline", "fault"):
            result["connected"] = False
            result["issues"].append(f"Device status is {slot.device_status}")
            return result

        # Check battery not critical
        if slot.battery_percent is not None and slot.battery_percent < 5:
            result["issues"].append(f"Battery critically low: {slot.battery_percent}%")

        # Check network connectivity (basic)
        now = timezone.now()
        if slot.charger.last_seen:
            time_delta = (now - slot.charger.last_seen).total_seconds()
            if time_delta > ConnectionValidationService.HEARTBEAT_TIMEOUT_SECONDS:
                result["connected"] = False
                timeout_str = ConnectionValidationService.HEARTBEAT_TIMEOUT_SECONDS
                result["issues"].append(
                    f"Charger not seen for {time_delta:.0f}s (timeout: {timeout_str}s)"
                )
                return result

        # All checks passed
        result["connected"] = True
        result["is_valid"] = len(result["issues"]) == 0  # Valid only if no issues

        return result

    @staticmethod
    def check_charger_health(charger_id: int) -> dict[str, Any]:
        """Check overall health of a charger and its slots.

        Args:
            charger_id: Charger model ID

        Returns:
            Dict with charger health status and slot details
        """
        try:
            charger = Charger.objects.prefetch_related("slots").get(id=charger_id)
        except Charger.DoesNotExist:
            return {
                "charger_id": charger_id,
                "found": False,
                "health": "unknown",
            }

        now = timezone.now()
        time_since_heartbeat = (
            (now - charger.last_seen).total_seconds() if charger.last_seen else float("inf")
        )

        charger_connected = (
            time_since_heartbeat <= ConnectionValidationService.HEARTBEAT_TIMEOUT_SECONDS
        )

        slots_data = []
        occupied_count = 0
        connected_count = 0
        issues_count = 0

        for slot in charger.slots.all().order_by("slot_number"):
            slot_check = ConnectionValidationService.check_slot_connection(slot)
            slots_data.append(slot_check)

            if slot.occupied:
                occupied_count += 1
                if slot_check["connected"]:
                    connected_count += 1
                if slot_check["issues"]:
                    issues_count += len(slot_check["issues"])

        # Determine overall health
        if not charger_connected:
            health = "offline"
        elif issues_count > 0:
            health = "degraded"
        elif occupied_count == 0:
            health = "idle"
        else:
            health = "healthy"

        return {
            "charger": {
                "id": charger.id,
                "name": charger.name,
                "status": charger.status,
                "ip": str(charger.ip) if charger.ip else None,
            },
            "health": health,
            "connected": charger_connected,
            "last_heartbeat_seconds_ago": int(time_since_heartbeat),
            "occupied_slots": occupied_count,
            "connected_slots": connected_count,
            "total_slots": charger.slot_count,
            "issue_count": issues_count,
            "slots": slots_data,
        }

    @staticmethod
    def check_location_charger_health(location_id: int) -> dict[str, Any]:
        """Check health of all chargers in a location.

        Args:
            location_id: Location model ID

        Returns:
            Dict with overall health and per-charger details
        """
        chargers = Charger.objects.filter(location_id=location_id, is_active=True)

        health_data = {
            "location_id": location_id,
            "charger_count": chargers.count(),
            "overall_health": "unknown",
            "chargers": [],
        }

        if chargers.count() == 0:
            return health_data

        charger_healths = []
        for charger in chargers:
            check = ConnectionValidationService.check_charger_health(charger.id)
            health_data["chargers"].append(check)
            charger_healths.append(check["health"])

        # Overall health is worst of all chargers
        health_priority = {"offline": 0, "degraded": 1, "idle": 2, "healthy": 3}
        worst_health = min((health_priority.get(h, -1) for h in charger_healths), default=-1)
        overall = [k for k, v in health_priority.items() if v == worst_health][0]

        health_data["overall_health"] = overall

        return health_data

    @staticmethod
    def validate_device_on_slot(
        slot: ChargerSlot,
        expected_serial: str | None = None,
    ) -> bool:
        """Validate that a specific device is on a charger slot.

        Args:
            slot: ChargerSlot instance
            expected_serial: Expected device serial (if any)

        Returns:
            True if slot is valid and connected, False otherwise
        """
        check = ConnectionValidationService.check_slot_connection(slot)

        if not check["is_valid"]:
            return False

        if expected_serial and slot.device_serial != expected_serial:
            logger.warning(
                f"Device mismatch: expected {expected_serial}, found {slot.device_serial} on {slot}"
            )
            return False

        return True

    @staticmethod
    def get_unhealthy_slots(charger_id: int) -> list[dict[str, Any]]:
        """Get all unhealthy slots in a charger.

        Args:
            charger_id: Charger model ID

        Returns:
            List of slot check dicts with issues
        """
        try:
            charger = Charger.objects.prefetch_related("slots").get(id=charger_id)
        except Charger.DoesNotExist:
            return []

        unhealthy = []
        for slot in charger.slots.all():
            check = ConnectionValidationService.check_slot_connection(slot)
            if not check["is_valid"] or check["issues"]:
                unhealthy.append(check)

        return unhealthy

    @staticmethod
    def get_all_unhealthy_slots(location_id: int) -> list[dict[str, Any]]:
        """Get all unhealthy slots across a location's chargers.

        Args:
            location_id: Location model ID

        Returns:
            List of slot check dicts with charger info
        """
        chargers = Charger.objects.filter(location_id=location_id, is_active=True)

        all_unhealthy = []
        for charger in chargers:
            unhealthy = ConnectionValidationService.get_unhealthy_slots(charger.id)
            for slot_check in unhealthy:
                slot_check["charger_name"] = charger.name
                all_unhealthy.append(slot_check)

        return all_unhealthy
