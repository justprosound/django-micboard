"""Service functions for WirelessUnit business logic.

Provides query and computation functions for wireless field device lifecycle,
separated from the model layer per ADR-002.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from django.utils import timezone

if TYPE_CHECKING:
    from micboard.models.hardware.wireless_unit import WirelessUnit
    from micboard.models.rf_coordination.rf_channel import RFChannel

logger = logging.getLogger(__name__)


_UNKNOWN_BYTE_VALUE = 255
_VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "discovered": {"provisioning", "offline", "retired"},
    "provisioning": {"online", "offline", "discovered"},
    "online": {"degraded", "idle", "offline", "maintenance"},
    "degraded": {"online", "idle", "offline", "maintenance"},
    "idle": {"online", "offline", "maintenance", "retired"},
    "offline": {"online", "degraded", "idle", "maintenance", "retired"},
    "maintenance": {"online", "offline", "retired"},
    "retired": set(),
}


def get_battery_percentage(unit: WirelessUnit) -> int | None:
    """Get battery level as percentage of 255-scale raw value."""
    if unit.battery == _UNKNOWN_BYTE_VALUE:
        return None
    return min(100, max(0, unit.battery * 100 // _UNKNOWN_BYTE_VALUE))


def get_battery_health(unit: WirelessUnit) -> str:
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


def get_battery_health_display_icon(unit: WirelessUnit) -> str:
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


def is_active_at_time(unit: WirelessUnit, at_time: datetime | None = None) -> bool:
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


def get_signal_quality(unit: WirelessUnit) -> str:
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


def is_transmitter(unit: WirelessUnit) -> bool:
    """Check if this unit transmits microphone audio."""
    return unit.device_type in ("mic_transmitter", "transceiver")


def get_transmitter_metrics(unit: WirelessUnit) -> dict[str, int | str]:
    """Get transmitter-specific metrics (mic audio, RF level)."""
    if not is_transmitter(unit):
        return {}
    return {
        "audio_level": unit.audio_level,
        "rf_level": unit.rf_level,
        "quality": get_signal_quality(unit),
        "frequency": unit.frequency,
    }


def is_iem_receiver(unit: WirelessUnit) -> bool:
    """Check if this unit receives IEM mix."""
    return unit.device_type in ("iem_receiver", "transceiver")


def get_iem_metrics(unit: WirelessUnit) -> dict[str, int | None]:
    """Get IEM receiver-specific metrics (link quality, mix level)."""
    if not is_iem_receiver(unit):
        return {}
    return {
        "iem_link_quality": unit.iem_link_quality,
        "iem_audio_level": unit.iem_audio_level,
    }


def get_assigned_rf_channel(unit: WirelessUnit) -> RFChannel | None:
    """Get the RFChannel this unit is assigned to, if any."""
    if hasattr(unit, "active_on_receive_channels"):
        active_channel = unit.active_on_receive_channels.first()
        if active_channel:
            return active_channel

    if hasattr(unit, "assigned_resource") and unit.assigned_resource:
        return unit.assigned_resource

    return None


def get_regulatory_status(unit: WirelessUnit) -> dict[str, str | bool | float | None]:
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


def prepare_unit_for_save(unit: WirelessUnit) -> dict[str, Any]:
    """Validate lifecycle changes and prepare derived fields before persistence."""
    if unit._state.adding:
        return {
            "old_status": None,
            "old_battery": None,
            "status_changed": False,
            "battery_changed": False,
            "update_fields": set(),
        }

    previous = type(unit).objects.only("status", "battery").get(pk=unit.pk)
    status_changed = previous.status != unit.status
    battery_changed = previous.battery != unit.battery
    update_fields: set[str] = set()

    if status_changed:
        allowed = _VALID_STATUS_TRANSITIONS.get(previous.status, set())
        if unit.status not in allowed:
            allowed_label = ", ".join(sorted(allowed)) if allowed else "none (terminal state)"
            raise ValueError(
                "Invalid status transition: "
                f"{previous.status} → {unit.status}. Allowed: {allowed_label}"
            )

        if unit.status in {"online", "degraded", "offline"}:
            unit.last_seen = timezone.now()
            update_fields.add("last_seen")

    return {
        "old_status": previous.status,
        "old_battery": previous.battery,
        "status_changed": status_changed,
        "battery_changed": battery_changed,
        "update_fields": update_fields,
    }


def finalize_unit_save(unit: WirelessUnit, context: dict[str, Any]) -> None:
    """Write lifecycle audit events after a wireless unit is persisted."""
    from micboard.services.maintenance.audit import AuditService

    if context["status_changed"]:
        AuditService.log_activity(
            activity_type="wireless_unit",
            operation="status_change",
            summary=(f"Wireless unit status changed: {context['old_status']} → {unit.status}"),
            obj=unit,
            old_values={"status": context["old_status"]},
            new_values={"status": unit.status},
        )

    if not context["battery_changed"] or unit.battery == _UNKNOWN_BYTE_VALUE:
        return

    old_battery = context["old_battery"]
    if old_battery is None or old_battery == _UNKNOWN_BYTE_VALUE:
        return

    old_pct = min(100, max(0, old_battery * 100 // _UNKNOWN_BYTE_VALUE))
    new_pct = get_battery_percentage(unit)
    if new_pct is None or new_pct >= old_pct:
        return

    crossed_threshold = next(
        (threshold for threshold in (15, 25) if old_pct > threshold >= new_pct),
        None,
    )
    if crossed_threshold is None:
        return

    AuditService.log_activity(
        activity_type="wireless_unit",
        operation="battery_warning",
        summary=f"Wireless unit battery: {new_pct}%",
        obj=unit,
        old_values={"battery_percentage": old_pct},
        new_values={"battery_percentage": new_pct},
        status="warning",
        log_mode="passive" if new_pct <= 15 else "normal",
    )
