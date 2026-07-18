"""Service functions for RFChannel business logic.

Provides regulatory domain resolution, coverage checking, and status
reporting for RF channels, separated from the model layer per ADR-002.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from micboard.services.hardware.dtos import RegulatoryDomainDTO

if TYPE_CHECKING:
    from micboard.models.locations.structure import Location
    from micboard.models.rf_coordination.compliance import RegulatoryDomain
    from micboard.models.rf_coordination.rf_channel import RFChannel

logger = logging.getLogger(__name__)

_VALID_RESOURCE_STATE_TRANSITIONS: dict[str, set[str]] = {
    "free": {"reserved", "active", "disabled"},
    "reserved": {"free", "active", "disabled"},
    "active": {"free", "degraded", "disabled"},
    "degraded": {"free", "active", "disabled"},
    "disabled": {"free"},
}


def get_regulatory_domain_for_location(location: Location | None) -> RegulatoryDomain | None:
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
        return cast("RegulatoryDomain", building.regulatory_domain)

    if building.country:
        from micboard.models.rf_coordination.compliance import RegulatoryDomain

        return RegulatoryDomain.objects.filter(country_code=building.country.upper()).first()

    return None


def get_regulatory_domain(channel: RFChannel) -> RegulatoryDomain | None:
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

    return domain.min_frequency_mhz <= channel.frequency <= domain.max_frequency_mhz


def get_needs_regulatory_update(channel: RFChannel) -> bool:
    """Flag indicating admin needs to update regulatory information.

    Returns True if channel is active with frequency but no regulatory coverage.
    """
    if channel.resource_state not in ("active", "reserved"):
        return False

    if not channel.frequency:
        return False

    return not has_regulatory_coverage(channel)


def get_regulatory_status_for_domain(
    channel: RFChannel,
    regulatory_domain: RegulatoryDomain | RegulatoryDomainDTO | None,
) -> dict[str, str | bool | float | None]:
    """Build regulatory status from an already-resolved domain projection.

    Query-oriented callers use this boundary to avoid resolving the same domain
    once per rendered row.
    """
    frequency = channel.frequency
    coverage = bool(
        regulatory_domain
        and frequency
        and regulatory_domain.min_frequency_mhz <= frequency <= regulatory_domain.max_frequency_mhz
    )
    needs_update = bool(
        channel.resource_state in ("active", "reserved") and frequency and not coverage
    )

    status: dict[str, str | bool | float | None] = {
        "has_coverage": coverage,
        "regulatory_domain": regulatory_domain.code if regulatory_domain else None,
        "operating_frequency_mhz": frequency,
        "needs_update": needs_update,
    }

    if not regulatory_domain:
        status["message"] = "\u26a0\ufe0f No regulatory domain set for chassis location"
    elif not frequency:
        status["message"] = "\u2139\ufe0f No operating frequency configured"
    elif not coverage:
        status["message"] = (
            f"\u26a0\ufe0f Frequency {frequency} MHz not covered by {regulatory_domain.code} "
            "regulatory data - admin needs to update"
        )
    else:
        status["message"] = f"\u2705 Regulatory coverage OK ({regulatory_domain.code})"

    return status


def get_regulatory_status(channel: RFChannel) -> dict[str, str | bool | float | None]:
    """Get comprehensive regulatory status information for admin UI."""
    return get_regulatory_status_for_domain(channel, get_regulatory_domain(channel))


def is_receive_channel(channel: RFChannel) -> bool:
    """Check if this is a receive-direction channel."""
    return channel.link_direction in ("receive", "bidirectional")


def is_send_channel(channel: RFChannel) -> bool:
    """Check if this is a send-direction channel."""
    return channel.link_direction in ("send", "bidirectional")


def prepare_channel_for_save(channel: RFChannel, *, using: str = "default") -> dict[str, Any]:
    """Validate a channel and prepare derived lifecycle fields for persistence."""
    from django.core.exceptions import ValidationError

    context: dict[str, Any] = {
        "old_resource_state": None,
        "state_changed": False,
        "update_fields": set(),
    }
    if not channel._state.adding:
        previous = (
            type(channel).objects.using(using).only("resource_state", "enabled").get(pk=channel.pk)
        )
        context["old_resource_state"] = previous.resource_state

        if previous.enabled and not channel.enabled:
            channel.resource_state = "disabled"
            context["update_fields"].add("resource_state")

        if previous.resource_state != channel.resource_state:
            allowed = _VALID_RESOURCE_STATE_TRANSITIONS.get(previous.resource_state, set())
            if channel.resource_state not in allowed:
                allowed_label = ", ".join(sorted(allowed)) if allowed else "none (terminal state)"
                raise ValueError(
                    "Invalid resource_state transition: "
                    f"{previous.resource_state} → {channel.resource_state}. "
                    f"Allowed: {allowed_label}"
                )
            context["state_changed"] = True

    expected_count = channel.chassis.get_expected_channel_count()
    if not channel.chassis.wmas_capable and channel.channel_number > expected_count:
        raise ValidationError(
            f"Channel {channel.channel_number} exceeds {channel.chassis.model} capacity "
            f"({expected_count} channels max)"
        )
    if channel.channel_number < 1:
        raise ValidationError("Channel number must be at least 1")

    return context


def finalize_channel_save(
    channel: RFChannel,
    context: dict[str, Any],
    *,
    using: str = "default",
) -> None:
    """Write the audit event for a persisted channel state transition."""
    if context["state_changed"]:
        from micboard.services.maintenance.audit import AuditService

        AuditService.log_activity(
            activity_type="rf_channel",
            operation="resource_state_change",
            summary=(
                "RF channel resource state changed: "
                f"{context['old_resource_state']} → {channel.resource_state}"
            ),
            obj=channel,
            old_values={"resource_state": context["old_resource_state"]},
            new_values={"resource_state": channel.resource_state},
            using=using,
        )
