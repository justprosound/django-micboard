"""Service functions for WirelessChassis business logic.

Provides chassis lifecycle, band plan detection, and status reporting,
separated from the model layer per ADR-002.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from django.utils import timezone

if TYPE_CHECKING:
    from micboard.models.hardware.wireless_chassis import WirelessChassis

logger = logging.getLogger(__name__)


_ACTIVE_STATES: set[str] = {"online", "degraded", "provisioning"}
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


def is_active_at_time(chassis: WirelessChassis, at_time: datetime | None = None) -> bool:
    """Check if chassis is active at given time (or now).

    Active states: online, degraded, provisioning.
    """
    return chassis.status in _ACTIVE_STATES


def get_band_plan_status(chassis: WirelessChassis) -> bool:
    """Check if chassis has band plan information configured.

    Returns True if band plan min/max are populated and max > min.
    """
    return (
        chassis.band_plan_min_mhz is not None
        and chassis.band_plan_max_mhz is not None
        and chassis.band_plan_max_mhz > chassis.band_plan_min_mhz
    )


def get_available_band_plans(chassis: WirelessChassis) -> list[tuple[str, str]]:
    """Get list of available band plans for this chassis's manufacturer.

    Returns list of (key, name) tuples for standard band plans.
    Empty list if manufacturer not set or no plans available.
    """
    if not chassis.manufacturer:
        return []

    mfg_code = chassis.manufacturer.code.lower() if hasattr(chassis.manufacturer, "code") else None
    if not mfg_code:
        return []

    from micboard.models.band_plans import get_available_band_plans as _get_plans

    return _get_plans(manufacturer=mfg_code)


def detect_band_plan_from_api_data(
    chassis: WirelessChassis, *, api_band_value: str | None
) -> dict[str, Any]:
    """Detect band plan from Shure/Sennheiser API frequencyBand value.

    Args:
        chassis: The WirelessChassis instance
        api_band_value: frequencyBand string from API (e.g., "G50", "G50 (470-534)")

    Returns:
        Dict with detected values and metadata:
        - band_plan_name: Resolved band plan name
        - band_plan_min_mhz: Minimum frequency
        - band_plan_max_mhz: Maximum frequency
        - source: "api" if from API, "model" if inferred from model code
        - message: Human-readable explanation
    """
    if not chassis.manufacturer:
        return {
            "band_plan_name": None,
            "band_plan_min_mhz": None,
            "band_plan_max_mhz": None,
            "source": None,
            "message": "Manufacturer not set",
        }

    mfg_code = (
        chassis.manufacturer.code.lower() if hasattr(chassis.manufacturer, "code") else "unknown"
    )

    from micboard.models.band_plans import (
        detect_band_plan_from_api_string,
        get_band_plan,
        get_band_plan_from_model_code,
    )

    if api_band_value:
        detected_name = detect_band_plan_from_api_string(
            api_band_value=api_band_value, manufacturer=mfg_code
        )
        if detected_name:
            band_plan = get_band_plan(
                manufacturer=mfg_code,
                band_plan_key=detected_name.lower().replace(" ", "_").replace("-", "_"),
            )
            if band_plan:
                return {
                    "band_plan_name": detected_name,
                    "band_plan_min_mhz": band_plan["min_mhz"],
                    "band_plan_max_mhz": band_plan["max_mhz"],
                    "source": "api",
                    "message": f"Detected from API frequencyBand '{api_band_value}'",
                }

    if chassis.model:
        detected_name = get_band_plan_from_model_code(manufacturer=mfg_code, model=chassis.model)
        if detected_name:
            band_plan = get_band_plan(
                manufacturer=mfg_code,
                band_plan_key=detected_name.lower().replace(" ", "_").replace("-", "_"),
            )
            if band_plan:
                return {
                    "band_plan_name": detected_name,
                    "band_plan_min_mhz": band_plan["min_mhz"],
                    "band_plan_max_mhz": band_plan["max_mhz"],
                    "source": "model",
                    "message": f"Inferred from model code '{chassis.model}'",
                }

    return {
        "band_plan_name": None,
        "band_plan_min_mhz": None,
        "band_plan_max_mhz": None,
        "source": None,
        "message": "No band plan detected from API or model",
    }


def apply_detected_band_plan(
    chassis: WirelessChassis, *, api_band_value: str | None = None
) -> bool:
    """Auto-detect and apply band plan information to this chassis.

    Takes the output of detect_band_plan_from_api_data() and applies it
    to the chassis fields.

    Args:
        chassis: The WirelessChassis instance
        api_band_value: API frequencyBand value (optional - uses model
                       detection if not provided)

    Returns:
        True if band plan was detected and applied, False otherwise
    """
    detected = detect_band_plan_from_api_data(chassis, api_band_value=api_band_value)
    if detected.get("band_plan_name"):
        chassis.band_plan_name = detected["band_plan_name"]
        chassis.band_plan_min_mhz = detected["band_plan_min_mhz"]
        chassis.band_plan_max_mhz = detected["band_plan_max_mhz"]
        return True
    return False


def _prepare_lifecycle_fields(
    chassis: WirelessChassis, *, created: bool
) -> tuple[str | None, set[str]]:
    """Validate a status transition and update lifecycle fields."""
    old_status: str | None = None
    lifecycle_update_fields: set[str] = set()
    if created:
        if chassis.status not in _OPERATIONAL_STATES:
            return old_status, lifecycle_update_fields
        chassis.is_online = True
        chassis.last_online_at = timezone.now()
        lifecycle_update_fields.update({"is_online", "last_online_at"})
        return old_status, lifecycle_update_fields

    previous = (
        type(chassis)
        .objects.only(
            "status",
            "is_online",
            "last_online_at",
            "total_uptime_minutes",
        )
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


def _manufacturer_code(chassis: WirelessChassis) -> str:
    return (
        chassis.manufacturer.code.lower()
        if chassis.manufacturer and hasattr(chassis.manufacturer, "code")
        else "unknown"
    )


def _apply_band_plan_fields(chassis: WirelessChassis, band_plan: dict[str, Any]) -> None:
    chassis.band_plan_min_mhz = band_plan["min_mhz"]
    chassis.band_plan_max_mhz = band_plan["max_mhz"]


def _prepare_specs_and_band_plan(chassis: WirelessChassis) -> None:
    """Apply device specifications and fill any missing band-plan data."""
    if not chassis.manufacturer or not chassis.model:
        return

    from micboard.models.band_plans import (
        get_band_plan,
        get_band_plan_from_model_code,
        parse_band_plan_from_name,
    )
    from micboard.models.device_specs import get_device_role
    from micboard.services.core.device_specs import DeviceSpecService

    DeviceSpecService.apply_specs_to_chassis(chassis)
    mfg_code = _manufacturer_code(chassis)
    if not chassis.role:
        chassis.role = get_device_role(manufacturer=mfg_code, model=chassis.model)

    if chassis.band_plan_name:
        if not chassis.band_plan_min_mhz or not chassis.band_plan_max_mhz:
            parsed = parse_band_plan_from_name(name=chassis.band_plan_name)
            if parsed:
                _apply_band_plan_fields(chassis, parsed)
        return

    detected = get_band_plan_from_model_code(manufacturer=mfg_code, model=chassis.model)
    if not detected:
        return
    chassis.band_plan_name = detected
    band_plan = get_band_plan(
        manufacturer=mfg_code,
        band_plan_key=detected.lower().replace(" ", "_").replace("-", "_"),
    )
    if band_plan:
        _apply_band_plan_fields(chassis, band_plan)


def prepare_chassis_for_save(chassis: WirelessChassis) -> dict[str, Any]:
    """Prepare chassis for save by syncing lifecycle, specs, and band plan."""
    created = chassis._state.adding
    old_status, lifecycle_update_fields = _prepare_lifecycle_fields(chassis, created=created)
    _prepare_specs_and_band_plan(chassis)

    return {
        "created": created,
        "old_status": old_status,
        "status_changed": old_status is not None and old_status != chassis.status,
        "update_fields": lifecycle_update_fields,
    }


def finalize_chassis_save(chassis: WirelessChassis, context: dict[str, Any]) -> None:
    """Emit audit and realtime side effects after a persisted status change."""
    if not context["status_changed"]:
        return

    old_status = context["old_status"]

    from micboard.services.maintenance.audit import AuditService

    AuditService.log_activity(
        activity_type="hardware",
        operation="status_change",
        summary=f"Chassis status changed: {old_status} → {chassis.status}",
        obj=chassis,
        old_values={"status": old_status},
        new_values={"status": chassis.status},
    )

    from micboard.services.notification.broadcast_service import BroadcastService

    BroadcastService.broadcast_device_status(
        service_code=chassis.manufacturer.code,
        device_id=chassis.pk,
        device_type=type(chassis).__name__,
        status=chassis.status,
        is_active=chassis.is_online,
    )
