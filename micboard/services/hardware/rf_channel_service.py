"""Service functions for RFChannel business logic.

Provides regulatory domain resolution, coverage checking, and status
reporting for RF channels, separated from the model layer per ADR-002.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from micboard.models.rf_coordination import RegulatoryDomain as _RegulatoryDomain
    from micboard.models.rf_coordination.rf_channel import RFChannel

logger = logging.getLogger(__name__)


def get_regulatory_domain_for_location(location) -> _RegulatoryDomain | None:
    """Get the applicable regulatory domain for a geographic location.

    This is the single source of truth for location → regulatory domain
    resolution, used by both RFChannel and WirelessChassis service functions.

    Returns the regulatory domain from:
    1. location.building.regulatory_domain (if set)
    2. location.building.country lookup
    3. None if no regulatory info available
    """
    if not location:
        return None

    building = getattr(location, "building", None)
    if not building:
        return None

    if building.regulatory_domain:
        return building.regulatory_domain

    if building.country:
        from micboard.models.rf_coordination import RegulatoryDomain

        return RegulatoryDomain.objects.filter(country_code=building.country.upper()).first()

    return None


def get_regulatory_domain(channel: RFChannel):
    """Get the applicable regulatory domain for an RF channel.

    Delegates to get_regulatory_domain_for_location for the actual resolution.
    """
    if not channel.chassis:
        return None
    return get_regulatory_domain_for_location(channel.chassis.location)


def has_regulatory_coverage(channel: RFChannel) -> bool:
    """Check if channel frequency has regulatory data coverage.

    Returns True if frequency is within regulatory domain's allowed bands.
    """
    domain = get_regulatory_domain(channel)
    if not domain or not channel.frequency:
        return False

    if domain.min_frequency_mhz <= channel.frequency <= domain.max_frequency_mhz:
        return True

    from micboard.models.rf_coordination import FrequencyBand

    return FrequencyBand.objects.filter(
        regulatory_domain=domain,
        start_frequency_mhz__lte=channel.frequency,
        end_frequency_mhz__gte=channel.frequency,
    ).exists()


def get_needs_regulatory_update(channel: RFChannel) -> bool:
    """Flag indicating admin needs to update regulatory information.

    Returns True if channel is active with frequency but no regulatory coverage.
    """
    if channel.resource_state not in ("active", "reserved"):
        return False

    if not channel.frequency:
        return False

    return not has_regulatory_coverage(channel)


def get_regulatory_status(channel: RFChannel) -> dict[str, str | bool | float | None]:
    """Get comprehensive regulatory status information for admin UI.

    Returns dict with regulatory coverage status and admin action flags.
    """
    domain = get_regulatory_domain(channel)
    coverage = has_regulatory_coverage(channel)

    status: dict[str, str | bool | float | None] = {
        "has_coverage": coverage,
        "regulatory_domain": domain.code if domain else None,
        "operating_frequency_mhz": channel.frequency,
        "needs_update": get_needs_regulatory_update(channel),
    }

    if not domain:
        status["message"] = "\u26a0\ufe0f No regulatory domain set for chassis location"
    elif not channel.frequency:
        status["message"] = "\u2139\ufe0f No operating frequency configured"
    elif not coverage:
        status["message"] = (
            f"\u26a0\ufe0f Frequency {channel.frequency} MHz not covered by {domain.code} "
            "regulatory data - admin needs to update"
        )
    else:
        status["message"] = f"\u2705 Regulatory coverage OK ({domain.code})"

    return status


def is_receive_channel(channel: RFChannel) -> bool:
    """Check if this is a receive-direction channel."""
    return channel.link_direction in ("receive", "bidirectional")


def is_send_channel(channel: RFChannel) -> bool:
    """Check if this is a send-direction channel."""
    return channel.link_direction in ("send", "bidirectional")


def validate_and_save_channel(channel: RFChannel, *args, **kwargs) -> None:
    """Validate channel numbering and save.

    Allows WMAS-capable chassis to exceed static channel counts.
    """
    from django.core.exceptions import ValidationError

    expected_count = channel.chassis.get_expected_channel_count()
    if not channel.chassis.wmas_capable and channel.channel_number > expected_count:
        raise ValidationError(
            f"Channel {channel.channel_number} exceeds {channel.chassis.model} capacity "
            f"({expected_count} channels max)"
        )
    if channel.channel_number < 1:
        raise ValidationError("Channel number must be at least 1")

    from micboard.models.rf_coordination.rf_channel import RFChannel as _RFChannel

    super(_RFChannel, channel).save(*args, **kwargs)
