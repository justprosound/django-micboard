"""Service functions for WirelessUnit business logic.

Provides query and computation functions for wireless field device lifecycle,
separated from the model layer per ADR-002.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


_UNKNOWN_BYTE_VALUE = 255


def get_battery_percentage(unit) -> int | None:
    """Get battery level as percentage of 255-scale raw value."""
    if unit.battery == _UNKNOWN_BYTE_VALUE:
        return None
    return min(100, max(0, unit.battery * 100 // _UNKNOWN_BYTE_VALUE))


def get_battery_health(unit) -> str:
    """Get battery health status.

    Returns manufacturer API battery_health if available,
    otherwise computes from battery_percentage.
    """
    if unit.battery_health and unit.battery_health != "unknown":
        return unit.battery_health

    pct = get_battery_percentage(unit)
    if pct is None:
        return "unknown"
    if pct > 50:
        return "good"
    if pct > 25:
        return "fair"
    if pct > 10:
        return "poor"
    return "critical"


def get_battery_health_display_icon(unit) -> str:
    """Get visual icon for battery health."""
    health = get_battery_health(unit)
    icons = {
        "excellent": "\U0001f50b\u2728",
        "good": "\U0001f50b",
        "fair": "\U0001f50b\u26a0\ufe0f",
        "poor": "\U0001faab",
        "critical": "\U0001faab\u2757",
        "unknown": "\u2753",
    }
    return icons.get(health, "\u2753")


def is_active_at_time(unit, at_time: datetime | None = None) -> bool:
    """Check if unit is active at given time (or now)."""
    check_time = at_time or timezone.now()
    active_states = ["online", "degraded", "provisioning"]
    if unit.status not in active_states:
        return False

    ref_time = unit.last_seen or unit.updated_at
    if not ref_time:
        return False

    time_since = check_time - ref_time
    return time_since < timedelta(minutes=5)


def get_signal_quality(unit) -> str:
    """Get signal quality as text from 0-255 quality value."""
    if unit.quality == _UNKNOWN_BYTE_VALUE:
        return "unknown"
    if unit.quality > 200:
        return "excellent"
    if unit.quality > 150:
        return "good"
    if unit.quality > 100:
        return "fair"
    return "poor"


def is_transmitter(unit) -> bool:
    """Check if this unit transmits microphone audio."""
    return unit.device_type in ("mic_transmitter", "transceiver")


def get_transmitter_metrics(unit) -> dict:
    """Get transmitter-specific metrics (mic audio, RF level)."""
    if not is_transmitter(unit):
        return {}
    return {
        "audio_level": unit.audio_level,
        "rf_level": unit.rf_level,
        "quality": get_signal_quality(unit),
        "frequency": unit.frequency,
    }


def is_iem_receiver(unit) -> bool:
    """Check if this unit receives IEM mix."""
    return unit.device_type in ("iem_receiver", "transceiver")


def get_iem_metrics(unit) -> dict:
    """Get IEM receiver-specific metrics (link quality, mix level)."""
    if not is_iem_receiver(unit):
        return {}
    return {
        "iem_link_quality": unit.iem_link_quality,
        "iem_audio_level": unit.iem_audio_level,
    }


def get_assigned_rf_channel(unit):
    """Get the RFChannel this unit is assigned to, if any."""
    if hasattr(unit, "active_on_receive_channels"):
        return unit.active_on_receive_channels.first()

    if hasattr(unit, "assigned_resource") and unit.assigned_resource:
        return unit.assigned_resource

    return None


def get_regulatory_status(unit) -> dict:
    """Get regulatory status by delegating to the assigned RFChannel."""
    rf_channel = get_assigned_rf_channel(unit)

    if rf_channel:
        from micboard.services.hardware.rf_channel_service import (
            get_regulatory_status as _get_status,
        )

        status = _get_status(rf_channel)
        status["source"] = "rf_channel"
        status["message"] = f"Via RFChannel {rf_channel.channel_number}: {status['message']}"
        return status

    return {
        "has_coverage": False,
        "regulatory_domain": None,
        "operating_frequency_mhz": None,
        "needs_update": False,
        "source": "no_channel",
        "message": "\u2139\ufe0f No RF channel assigned - regulatory check not applicable",
    }
