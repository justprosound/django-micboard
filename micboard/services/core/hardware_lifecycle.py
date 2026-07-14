"""Device lifecycle management service.

Handles all device state transitions, validation, and bi-directional sync
with manufacturer APIs. Replaces signal-based state management with direct,
testable method calls.

State Transitions:
    DISCOVERED → PROVISIONING → ONLINE
                              ↓
                         DEGRADED → MAINTENANCE
                              ↓
                         OFFLINE → RETIRED
"""

from __future__ import annotations

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
    RETIRED = "retired"  # Permanently decommissioned


class HardwareLifecycleManager:
    """Centralized manager for device lifecycle operations.

    Handles:
    - State transitions with validation
    - Bi-directional sync with manufacturer APIs
    - Health monitoring

    Does NOT use signals for state management (signals only for broadcasts).
    """

    # Valid state transitions (from_state -> [to_states])
    VALID_TRANSITIONS: dict[str, list[str]] = {
        HardwareStatus.DISCOVERED.value: [
            HardwareStatus.PROVISIONING.value,
            HardwareStatus.OFFLINE.value,
            HardwareStatus.RETIRED.value,
        ],
        HardwareStatus.PROVISIONING.value: [
            HardwareStatus.ONLINE.value,
            HardwareStatus.OFFLINE.value,
            HardwareStatus.DISCOVERED.value,
        ],
        HardwareStatus.ONLINE.value: [
            HardwareStatus.DEGRADED.value,
            HardwareStatus.OFFLINE.value,
            HardwareStatus.MAINTENANCE.value,
        ],
        HardwareStatus.DEGRADED.value: [
            HardwareStatus.ONLINE.value,
            HardwareStatus.OFFLINE.value,
            HardwareStatus.MAINTENANCE.value,
        ],
        HardwareStatus.OFFLINE.value: [
            HardwareStatus.ONLINE.value,
            HardwareStatus.DEGRADED.value,
            HardwareStatus.MAINTENANCE.value,
            HardwareStatus.RETIRED.value,
        ],
        HardwareStatus.MAINTENANCE.value: [
            HardwareStatus.ONLINE.value,
            HardwareStatus.OFFLINE.value,
            HardwareStatus.RETIRED.value,
        ],
        HardwareStatus.RETIRED.value: [],  # Terminal state
    }

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

        if not self._is_valid_transition(from_status, to_status):
            logger.warning(
                f"Invalid transition: {device_type} {device.pk} from {from_status} to {to_status}",
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
            f"Device transition: {device_type} {device.pk} {from_status} → {to_status}",
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

    def mark_offline(
        self, device: WirelessChassis | WirelessUnit, *, reason: str = "Not responding"
    ) -> bool:
        """Mark device as offline."""
        return self.transition_device(device, HardwareStatus.OFFLINE.value, reason=reason)

    # Helper methods

    def _is_valid_transition(self, from_status: str, to_status: str) -> bool:
        """Check if transition is valid."""
        if from_status == to_status:
            return True  # No-op transition
        return to_status in self.VALID_TRANSITIONS.get(from_status, [])


def map_api_state_to_status(api_state: str, current_status: str) -> str:
    """Map manufacturer API state to HardwareStatus."""
    state_mapping = {
        "ONLINE": HardwareStatus.ONLINE.value,
        "DISCOVERING": HardwareStatus.PROVISIONING.value,
        "OFFLINE": HardwareStatus.OFFLINE.value,
        "UNKNOWN": HardwareStatus.DISCOVERED.value,
    }
    return state_mapping.get(api_state, current_status)
