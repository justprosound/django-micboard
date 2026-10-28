"""Device lifecycle management service.

Handles all device state transitions, validation, and bi-directional sync
with manufacturer APIs. Replaces signal-based state management with direct,
testable method calls.

State Transitions (the allowed graph lives in this module; nothing else copies it):
    DISCOVERED → PROVISIONING → ONLINE
                              ↓
                         DEGRADED → MAINTENANCE
                              ↓
                         OFFLINE → RETIRED
"""

import logging
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from django.db import DEFAULT_DB_ALIAS, transaction
from django.utils import timezone

if TYPE_CHECKING:  # pragma: no cover
    from micboard.models.hardware.wireless_chassis import WirelessChassis
    from micboard.models.hardware.wireless_unit import WirelessUnit

logger = logging.getLogger(__name__)


class HardwareStatus(StrEnum):
    """Device lifecycle states."""

    DISCOVERED = "discovered"  # Found via discovery, not yet configured
    PROVISIONING = "provisioning"  # Being configured/registered
    ONLINE = "online"  # Fully operational
    DEGRADED = "degraded"  # Functional but with warnings
    OFFLINE = "offline"  # Not responding
    MAINTENANCE = "maintenance"  # Administratively disabled
    IDLE = "idle"  # Units only: powered and reachable but not in use
    RETIRED = "retired"  # Permanently decommissioned


class DeviceKind(StrEnum):
    """Which status graph a device follows."""

    CHASSIS = "chassis"
    UNIT = "unit"


_S = HardwareStatus
_CHASSIS_TRANSITIONS: dict[str, frozenset[str]] = {
    _S.DISCOVERED: frozenset({_S.PROVISIONING, _S.OFFLINE, _S.RETIRED}),
    _S.PROVISIONING: frozenset({_S.ONLINE, _S.OFFLINE, _S.DISCOVERED}),
    _S.ONLINE: frozenset({_S.DEGRADED, _S.OFFLINE, _S.MAINTENANCE}),
    _S.DEGRADED: frozenset({_S.ONLINE, _S.OFFLINE, _S.MAINTENANCE}),
    _S.OFFLINE: frozenset({_S.ONLINE, _S.DEGRADED, _S.MAINTENANCE, _S.RETIRED}),
    _S.MAINTENANCE: frozenset({_S.ONLINE, _S.OFFLINE, _S.RETIRED}),
    _S.RETIRED: frozenset(),  # Terminal state
}
# Units add IDLE: reachable from online/degraded/offline and able to leave it.
_UNIT_TRANSITIONS: dict[str, frozenset[str]] = {
    **_CHASSIS_TRANSITIONS,
    _S.ONLINE: _CHASSIS_TRANSITIONS[_S.ONLINE] | {_S.IDLE},
    _S.DEGRADED: _CHASSIS_TRANSITIONS[_S.DEGRADED] | {_S.IDLE},
    _S.OFFLINE: _CHASSIS_TRANSITIONS[_S.OFFLINE] | {_S.IDLE},
    _S.IDLE: frozenset({_S.ONLINE, _S.OFFLINE, _S.MAINTENANCE, _S.RETIRED}),
}
_GRAPHS: dict[DeviceKind, dict[str, frozenset[str]]] = {
    DeviceKind.CHASSIS: _CHASSIS_TRANSITIONS,
    DeviceKind.UNIT: _UNIT_TRANSITIONS,
}


# A responding device in one of these states is left exactly as it is.
_RESPONSE_KEEPS_STATUS = frozenset({_S.ONLINE, _S.DEGRADED, _S.MAINTENANCE})


def allowed_transitions(kind: DeviceKind, from_status: str) -> frozenset[str]:
    """Return the statuses a device may move to from ``from_status``."""
    return _GRAPHS[kind].get(from_status, frozenset())


def is_valid_transition(kind: DeviceKind, from_status: str, to_status: str) -> bool:
    """Check a status move; staying put is always allowed."""
    return from_status == to_status or to_status in allowed_transitions(kind, from_status)


def ensure_valid_transition(kind: DeviceKind, from_status: str, to_status: str) -> None:
    """Raise ``ValueError`` unless the move is allowed."""
    if is_valid_transition(kind, from_status, to_status):
        return
    allowed = allowed_transitions(kind, from_status)
    allowed_label = ", ".join(sorted(allowed)) if allowed else "none (terminal state)"
    raise ValueError(
        f"Invalid status transition: {from_status} → {to_status}. Allowed: {allowed_label}"
    )


def device_kind(device: WirelessChassis | WirelessUnit) -> DeviceKind:
    """Return which graph governs ``device``."""
    return DeviceKind.UNIT if device._meta.model_name == "wirelessunit" else DeviceKind.CHASSIS


class HardwareLifecycleManager:
    """Centralized manager for device lifecycle operations.

    Handles:
    - State transitions with validation
    - Bi-directional sync with manufacturer APIs
    - Health monitoring

    Does NOT use signals for state management (signals only for broadcasts).
    """

    def transition_device(
        self,
        device: WirelessChassis | WirelessUnit,
        to_status: str,
        *,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Transition a device on the database that supplied the instance."""
        using = device._state.db or DEFAULT_DB_ALIAS
        with transaction.atomic(using=using):
            return self._transition_device(
                device,
                to_status,
                reason=reason,
                metadata=metadata,
                using=using,
            )

    def _transition_device(
        self,
        device: WirelessChassis | WirelessUnit,
        to_status: str,
        *,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
        using: str = DEFAULT_DB_ALIAS,
    ) -> bool:
        """Transition device to new status with validation and logging.

        Args:
            device: Device instance to transition
            to_status: Target status
            reason: Human-readable reason for transition
            metadata: Additional context data
        Returns:
            True if transition succeeded, False otherwise
        """
        device_type = device.__class__.__name__

        # Lock before reading state so a stale caller cannot overwrite a newer transition.
        device = (
            device.__class__._default_manager.using(using).select_for_update().get(pk=device.pk)
        )
        from_status = device.status

        if not is_valid_transition(device_kind(device), from_status, to_status):
            logger.warning(
                "Invalid transition: %s %s from %s to %s",
                device_type,
                device.pk,
                from_status,
                to_status,
                extra={
                    "device_id": device.pk,
                    "device_type": device_type,
                    "from_status": from_status,
                    "to_status": to_status,
                },
            )
            return False

        # Update device status
        device.status = to_status
        device.last_seen = timezone.now()

        # WirelessUnit exposes an auto-managed updated_at field; WirelessChassis does not.
        update_fields = ["status", "last_seen"]
        if any(
            field.name == "updated_at" and field.concrete for field in device._meta.get_fields()
        ):
            update_fields.append("updated_at")
        device.save(update_fields=update_fields, using=using)

        logger.info(
            "Device transition: %s %s %s → %s",
            device_type,
            device.pk,
            from_status,
            to_status,
            extra={
                "device_id": device.pk,
                "device_type": device_type,
                "from_status": from_status,
                "to_status": to_status,
                "reason_provided": bool(reason),
                "has_metadata": bool(metadata),
            },
        )

        return True

    def mark_online(
        self,
        device: WirelessChassis | WirelessUnit,
        *,
        health_data: dict[str, Any] | None = None,
    ) -> bool:
        """Mark device as online/operational."""
        return self.transition_device(
            device,
            HardwareStatus.ONLINE.value,
            reason="Device responding to polls",
            metadata=health_data,
        )

    def bring_responding_online(self, chassis: WirelessChassis, *, reason: str) -> None:
        """Bring a chassis that just answered the vendor API to online.

        Degraded and maintenance are deliberate states a poll must not overwrite, and
        an online chassis needs nothing. A discovered chassis passes through
        provisioning. Raises ``RuntimeError`` if the graph refuses a step, so callers
        never carry on as if the chassis were online.
        """
        if chassis.status in _RESPONSE_KEEPS_STATUS:
            return
        if chassis.status == HardwareStatus.DISCOVERED and not self.transition_device(
            chassis, HardwareStatus.PROVISIONING, reason=reason
        ):
            raise RuntimeError(f"Could not provision wireless chassis {chassis.pk}")
        if not self.transition_device(chassis, HardwareStatus.ONLINE, reason=reason):
            raise RuntimeError(f"Could not mark wireless chassis {chassis.pk} online")
        chassis.refresh_from_db(fields=["status", "is_online", "last_online_at", "last_seen"])

    def mark_offline(
        self, device: WirelessChassis | WirelessUnit, *, reason: str = "Not responding"
    ) -> bool:
        """Mark device as offline."""
        return self.transition_device(device, HardwareStatus.OFFLINE.value, reason=reason)


def map_api_state_to_status(api_state: str, current_status: str) -> str:
    """Map manufacturer API state to HardwareStatus."""
    state_mapping = {
        "ONLINE": HardwareStatus.ONLINE.value,
        "DISCOVERING": HardwareStatus.PROVISIONING.value,
        "OFFLINE": HardwareStatus.OFFLINE.value,
        "UNKNOWN": HardwareStatus.DISCOVERED.value,
    }
    return state_mapping.get(api_state, current_status)
