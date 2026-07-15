"""Service functions for WirelessChassis regulatory domain logic.

Provides regulatory domain resolution, band plan coverage checking, and status
reporting for wireless chassis, separated from the model layer per ADR-002.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from micboard.services.hardware.dtos import BandPlanInfo
from micboard.services.hardware.rf_channel_service import (
    get_regulatory_domain_for_location,
)

if TYPE_CHECKING:
    from micboard.models.hardware.wireless_chassis import WirelessChassis

logger = logging.getLogger(__name__)


def get_band_plan_status(chassis: WirelessChassis) -> bool:
    """Return whether both chassis band-plan bounds form an ordered range."""
    return (
        chassis.band_plan_min_mhz is not None
        and chassis.band_plan_max_mhz is not None
        and chassis.band_plan_max_mhz > chassis.band_plan_min_mhz
    )


def detect_band_plan_from_api_data(
    chassis: WirelessChassis,
    *,
    api_band_value: str | None = None,
) -> BandPlanInfo:
    """Resolve chassis band-plan metadata from API evidence, then model evidence."""
    if not chassis.manufacturer:
        return BandPlanInfo(message="Manufacturer not set")

    manufacturer_code = getattr(chassis.manufacturer, "code", "unknown").lower()

    from micboard.models.band_plans import (
        detect_band_plan_from_api_string,
        get_band_plan,
        get_band_plan_from_model_code,
    )

    if api_band_value:
        detected_name = detect_band_plan_from_api_string(
            api_band_value=api_band_value,
            manufacturer=manufacturer_code,
        )
        if detected_name:
            detected = _detected_band_plan_info(
                manufacturer_code=manufacturer_code,
                detected_name=detected_name,
                source="api",
                message=f"Detected from API frequencyBand '{api_band_value}'",
                get_band_plan=get_band_plan,
            )
            if detected:
                return detected

    if chassis.model:
        detected_name = get_band_plan_from_model_code(
            manufacturer=manufacturer_code,
            model=chassis.model,
        )
        if detected_name:
            detected = _detected_band_plan_info(
                manufacturer_code=manufacturer_code,
                detected_name=detected_name,
                source="model",
                message=f"Inferred from model code '{chassis.model}'",
                get_band_plan=get_band_plan,
            )
            if detected:
                return detected

    return BandPlanInfo(message="No band plan detected from API or model")


def apply_detected_band_plan(
    chassis: WirelessChassis,
    *,
    api_band_value: str | None = None,
) -> bool:
    """Apply a detected band plan to a chassis, returning whether detection succeeded."""
    detected = detect_band_plan_from_api_data(chassis, api_band_value=api_band_value)
    if detected.name is None:
        return False
    chassis.band_plan_name = detected.name
    chassis.band_plan_min_mhz = detected.min_mhz
    chassis.band_plan_max_mhz = detected.max_mhz
    return True


def prepare_chassis_regulatory_fields(chassis: WirelessChassis) -> None:
    """Apply device specifications and fill missing chassis band-plan fields."""
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
    manufacturer_code = getattr(chassis.manufacturer, "code", "unknown").lower()
    if not chassis.role:
        chassis.role = get_device_role(manufacturer=manufacturer_code, model=chassis.model)

    if chassis.band_plan_name:
        if chassis.band_plan_min_mhz is None or chassis.band_plan_max_mhz is None:
            parsed = parse_band_plan_from_name(name=chassis.band_plan_name)
            if parsed:
                _apply_band_plan_fields(chassis, parsed)
        return

    detected_name = get_band_plan_from_model_code(
        manufacturer=manufacturer_code,
        model=chassis.model,
    )
    if not detected_name:
        return
    chassis.band_plan_name = detected_name
    band_plan = get_band_plan(
        manufacturer=manufacturer_code,
        band_plan_key=_band_plan_key(detected_name),
    )
    if band_plan:
        _apply_band_plan_fields(chassis, band_plan)


def _band_plan_key(name: str) -> str:
    return name.lower().replace(" ", "_").replace("-", "_")


def _detected_band_plan_info(
    *,
    manufacturer_code: str,
    detected_name: str,
    source: str,
    message: str,
    get_band_plan: Any,
) -> BandPlanInfo | None:
    band_plan = get_band_plan(
        manufacturer=manufacturer_code,
        band_plan_key=_band_plan_key(detected_name),
    )
    if not band_plan:
        return None
    return BandPlanInfo(
        name=detected_name,
        min_mhz=band_plan["min_mhz"],
        max_mhz=band_plan["max_mhz"],
        source=source,
        message=message,
    )


def _apply_band_plan_fields(chassis: WirelessChassis, band_plan: dict[str, Any]) -> None:
    chassis.band_plan_min_mhz = band_plan["min_mhz"]
    chassis.band_plan_max_mhz = band_plan["max_mhz"]


def has_band_plan_regulatory_coverage(chassis: WirelessChassis) -> bool:
    """Check if chassis's band plan has regulatory coverage.

    Returns True if the entire band plan range is covered by regulatory data.
    Returns False if no band plan, no regulatory domain, or insufficient coverage.
    """
    if not get_band_plan_status(chassis):
        return False

    domain = get_regulatory_domain_for_location(chassis.location)
    if not domain:
        return False

    band_min = chassis.band_plan_min_mhz
    band_max = chassis.band_plan_max_mhz
    if band_min is None or band_max is None:
        return False

    if domain.min_frequency_mhz <= band_min and domain.max_frequency_mhz >= band_max:
        return True

    from micboard.models.rf_coordination.compliance import FrequencyBand

    overlapping_bands = FrequencyBand.objects.filter(
        regulatory_domain=domain,
        start_frequency_mhz__lt=band_max,
        end_frequency_mhz__gt=band_min,
    ).exclude(band_type="forbidden")

    if not overlapping_bands.exists():
        return False

    covered_min = min(band.start_frequency_mhz for band in overlapping_bands)
    covered_max = max(band.end_frequency_mhz for band in overlapping_bands)

    return covered_min <= band_min and covered_max >= band_max


def get_needs_band_plan_regulatory_update(chassis: WirelessChassis) -> bool:
    """Flag indicating admin needs to update regulatory information for band plan.

    Returns True if:
    - Chassis is online
    - Has a band plan configured
    - But no regulatory coverage exists for that band plan
    """
    if chassis.status not in ("online", "degraded", "provisioning"):
        return False

    if not get_band_plan_status(chassis):
        return False

    return not has_band_plan_regulatory_coverage(chassis)


def get_band_plan_regulatory_status(chassis: WirelessChassis) -> dict[str, str | bool | None]:
    """Get comprehensive regulatory status for this chassis's band plan.

    Returns dict with:
    - has_band_plan: bool - Whether band plan is configured
    - has_coverage: bool - Whether regulatory data exists for band plan
    - regulatory_domain: str | None - Domain code (e.g., 'FCC', 'ETSI')
    - band_plan_range: str | None - Human-readable band plan range
    - needs_update: bool - Flag for admin attention
    - message: str - Human-readable status message
    """
    domain = get_regulatory_domain_for_location(chassis.location)
    has_plan = get_band_plan_status(chassis)
    has_coverage = has_band_plan_regulatory_coverage(chassis)

    band_plan_range = None
    if has_plan:
        band_plan_range = f"{chassis.band_plan_min_mhz}-{chassis.band_plan_max_mhz} MHz"
        if chassis.band_plan_name:
            band_plan_range = f"{chassis.band_plan_name} ({band_plan_range})"

    status = {
        "has_band_plan": has_plan,
        "has_coverage": has_coverage,
        "regulatory_domain": domain.code if domain else None,
        "band_plan_range": band_plan_range,
        "needs_update": get_needs_band_plan_regulatory_update(chassis),
    }

    if not domain:
        status["message"] = "\u26a0\ufe0f No regulatory domain set for chassis location"
    elif not has_plan:
        status["message"] = "\u2139\ufe0f No band plan configured"
    elif not has_coverage:
        status["message"] = (
            f"\u26a0\ufe0f Band plan {band_plan_range} not covered by {domain.code} "
            "regulatory data - admin needs to update"
        )
    else:
        status["message"] = f"\u2705 Band plan regulatory coverage OK ({domain.code})"

    return status
