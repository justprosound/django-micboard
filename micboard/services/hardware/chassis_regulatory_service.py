"""Service functions for WirelessChassis regulatory domain logic.

Provides regulatory domain resolution, band plan coverage checking, and status
reporting for wireless chassis, separated from the model layer per ADR-002.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from micboard.services.hardware.rf_channel_service import (
    get_regulatory_domain_for_location,
)
from micboard.services.hardware.wireless_chassis_service import get_band_plan_status

if TYPE_CHECKING:
    from micboard.models.hardware.wireless_chassis import WirelessChassis
    from micboard.models.rf_coordination.compliance import RegulatoryDomain

logger = logging.getLogger(__name__)


def get_regulatory_domain(chassis: WirelessChassis) -> RegulatoryDomain | None:
    """Get the applicable regulatory domain for a wireless chassis.

    Delegates to the shared location resolution function in rf_channel_service.
    """
    return get_regulatory_domain_for_location(chassis.location)


def has_band_plan_regulatory_coverage(chassis: WirelessChassis) -> bool:
    """Check if chassis's band plan has regulatory coverage.

    Returns True if the entire band plan range is covered by regulatory data.
    Returns False if no band plan, no regulatory domain, or insufficient coverage.
    """
    if not get_band_plan_status(chassis):
        return False

    domain = get_regulatory_domain(chassis)
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
    domain = get_regulatory_domain(chassis)
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
