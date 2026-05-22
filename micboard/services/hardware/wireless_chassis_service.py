"""Service functions for WirelessChassis business logic.

Provides chassis lifecycle, band plan detection, and status reporting,
separated from the model layer per ADR-002.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from micboard.models.hardware.wireless_chassis import WirelessChassis

logger = logging.getLogger(__name__)


_ACTIVE_STATES: set[str] = {"online", "degraded", "provisioning"}


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


def prepare_chassis_for_save(chassis: WirelessChassis) -> dict:
    """Prepare chassis for save by syncing specs and detecting band plan.

    Handles DeviceSpecService sync, role detection, and band plan resolution.
    Returns dict with 'created' boolean for post-save handling.
    """
    from micboard.services.core.device_specs import DeviceSpecService

    created = chassis.pk is None
    band_plan = None

    if chassis.manufacturer and chassis.model:
        DeviceSpecService.apply_specs_to_chassis(chassis)

        if not chassis.role:
            from micboard.models.device_specs import get_device_role

            mfg_code = (
                chassis.manufacturer.code.lower()
                if hasattr(chassis.manufacturer, "code")
                else "unknown"
            )
            chassis.role = get_device_role(
                manufacturer=mfg_code,
                model=chassis.model,
            )

        if band_plan:
            chassis.band_plan_min_mhz = band_plan["min_mhz"]
            chassis.band_plan_max_mhz = band_plan["max_mhz"]
        elif not chassis.band_plan_min_mhz or not chassis.band_plan_max_mhz:
            from micboard.models.band_plans import parse_band_plan_from_name

            parsed = parse_band_plan_from_name(name=chassis.band_plan_name)
            if parsed:
                chassis.band_plan_min_mhz = parsed["min_mhz"]
                chassis.band_plan_max_mhz = parsed["max_mhz"]
    elif not chassis.band_plan_name and chassis.manufacturer and chassis.model:
        from micboard.models.band_plans import (
            get_band_plan,
            get_band_plan_from_model_code,
        )

        mfg_code = (
            chassis.manufacturer.code.lower()
            if hasattr(chassis.manufacturer, "code")
            else "unknown"
        )
        detected = get_band_plan_from_model_code(manufacturer=mfg_code, model=chassis.model)
        if detected:
            chassis.band_plan_name = detected
            band_plan = get_band_plan(
                manufacturer=mfg_code,
                band_plan_key=detected.lower().replace(" ", "_").replace("-", "_"),
            )
            if band_plan:
                chassis.band_plan_min_mhz = band_plan["min_mhz"]
                chassis.band_plan_max_mhz = band_plan["max_mhz"]

    return {"created": created}
