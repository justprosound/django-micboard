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
from datetime import timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:  # pragma: no cover
    from micboard.models import WirelessChassis, WirelessUnit

logger = logging.getLogger(__name__)


class HardwareStatus(str, Enum):
    """Device lifecycle states."""

    DISCOVERED = "discovered"  # Found via discovery, not yet configured
    PROVISIONING = "provisioning"  # Being configured/registered
    ONLINE = "online"  # Fully operational
    DEGRADED = "degraded"  # Functional but with warnings
    OFFLINE = "offline"  # Not responding
    MAINTENANCE = "maintenance"  # Administratively disabled
    RETIRED = "retired"  # Permanently decommissioned

    @classmethod
    def choices(cls):
        """Django model choices format."""
        return [(status.value, status.name.replace("_", " ").title()) for status in cls]

    @classmethod
    def active_states(cls) -> list[str]:
        """States where device is considered active."""
        return [cls.ONLINE.value, cls.DEGRADED.value, cls.PROVISIONING.value]

    @classmethod
    def inactive_states(cls) -> list[str]:
        """States where device is considered inactive."""
        return [cls.OFFLINE.value, cls.MAINTENANCE.value, cls.RETIRED.value]


class HardwareLifecycleManager:
    """Centralized manager for device lifecycle operations.

    Handles:
    - State transitions with validation
    - Bi-directional sync with manufacturer APIs
    - Activity logging
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

    def __init__(
        self,
        service_code: str | None = None,
        *,
        structured_logger=None,
    ):
        """Initialize lifecycle manager.

        Args:
            service_code: Optional manufacturer service code for logging context
            structured_logger: Optional structured logger instance for consistent event formatting
        """
        self.service_code = service_code
        try:
            self._logger = structured_logger or get_structured_logger()
        except Exception:
            logger.debug("Falling back to standard logger; structured logger unavailable")
            self._logger = None

    def transition(
        self,
        device: WirelessChassis | WirelessUnit,
        to_status: str,
        *,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
        sync_to_api: bool = False,
    ) -> bool:
        """Public alias for transition_device for compatibility."""
        return self.transition_device(
            device,
            to_status,
            reason=reason,
            metadata=metadata,
            sync_to_api=sync_to_api,
        )

    @transaction.atomic
    def transition_device(
        self,
        device: WirelessChassis | WirelessUnit,
        to_status: str,
        *,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
        sync_to_api: bool = False,
    ) -> bool:
        """Transition device to new status with validation and logging.

        Args:
            device: Device instance to transition
            to_status: Target status
            reason: Human-readable reason for transition
            metadata: Additional context data
            sync_to_api: Whether to push change to manufacturer API

        Returns:
            True if transition succeeded, False otherwise
        """
        from_status = device.status
        device_type = device.__class__.__name__

        # Validate transition
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

        # Lock device row for update
        device = device.__class__.objects.select_for_update().get(pk=device.pk)

        # Store old values for logging
        old_values = {
            "status": from_status,
            "last_seen": device.last_seen,
        }

        # Update device status
        device.status = to_status
        device.last_seen = timezone.now()

        # Save with specific fields
        device.save(update_fields=["status", "last_seen", "updated_at"])

        # Log the transition
        if self._logger:
            self._logger.log_crud_update(
                device,
                old_values=old_values,
                new_values={
                    "status": to_status,
                    "last_seen": device.last_seen,
                },
            )

        logger.info(
            f"Device transition: {device_type} {device.pk} {from_status} → {to_status}",
            extra={
                "device_id": device.pk,
                "device_type": device_type,
                "from_status": from_status,
                "to_status": to_status,
                "reason": reason,
                "metadata": metadata or {},
            },
        )

        if sync_to_api and self.service_code:
            from .device_api_sync_service import _sync_status_to_api as _do_api_sync

            _do_api_sync(self.service_code, device, to_status, metadata)

        return True

    def mark_discovered(
        self,
        device: WirelessChassis | WirelessUnit,
        *,
        device_data: dict[str, Any] | None = None,
    ) -> bool:
        """Mark device as discovered."""
        return self.transition_device(
            device,
            HardwareStatus.DISCOVERED.value,
            reason="Device discovered via API",
            metadata=device_data,
        )

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

    def mark_degraded(
        self, device: WirelessChassis | WirelessUnit, *, warnings: list[str] | None = None
    ) -> bool:
        """Mark device as degraded (functional but with issues)."""
        return self.transition_device(
            device,
            HardwareStatus.DEGRADED.value,
            reason="Device has warnings or performance issues",
            metadata={"warnings": warnings or []},
        )

    def mark_offline(
        self, device: WirelessChassis | WirelessUnit, *, reason: str = "Not responding"
    ) -> bool:
        """Mark device as offline."""
        return self.transition_device(device, HardwareStatus.OFFLINE.value, reason=reason)

    def mark_maintenance(
        self, device: WirelessChassis | WirelessUnit, *, reason: str = "Administrative action"
    ) -> bool:
        """Mark device as in maintenance mode."""
        return self.transition_device(
            device,
            HardwareStatus.MAINTENANCE.value,
            reason=reason,
            sync_to_api=True,  # Push to API to disable alerts
        )

    def mark_retired(
        self, device: WirelessChassis | WirelessUnit, *, reason: str = "Decommissioned"
    ) -> bool:
        """Mark device as retired (terminal state)."""
        return self.transition_device(device, HardwareStatus.RETIRED.value, reason=reason)

    def update_stale_devices(self, *, timeout_minutes: int = 5) -> int:
        """Mark devices offline when last_seen is older than threshold."""
        from micboard.models import WirelessChassis

        threshold = timezone.now() - timedelta(minutes=timeout_minutes)
        stale = WirelessChassis.objects.filter(last_seen__lt=threshold).exclude(
            status__in=[HardwareStatus.MAINTENANCE.value, HardwareStatus.RETIRED.value]
        )

        updated = 0
        for device in stale:
            if self.mark_offline(device, reason="Stale heartbeat"):
                updated += 1
        return updated

    def create_with_state(self, manufacturer, api_data: dict[str, Any]) -> WirelessChassis | None:
        """Create a chassis with initial state from API data."""
        from micboard.models import WirelessChassis

        ip = api_data.get("ipAddress") or api_data.get("ip") or api_data.get("ipv4")
        api_device_id = api_data.get("id") or api_data.get("api_device_id")
        if not ip or not api_device_id:
            logger.warning("Skipping device creation; missing ip or api_device_id")
            return None

        chassis = WirelessChassis.objects.create(
            manufacturer=manufacturer,
            api_device_id=api_device_id,
            ip=ip,
            model=api_data.get("model", ""),
            serial_number=api_data.get("serialNumber", ""),
            status=self._map_api_state_to_status(
                api_data.get("deviceState", "").upper(), "discovered"
            ),
            last_seen=timezone.now(),
        )

        return chassis

    def handle_poll_result(
        self, device: WirelessChassis | WirelessUnit, poll_data: dict[str, Any]
    ) -> bool:
        """Handle lifecycle transition from poll results."""
        state = poll_data.get("deviceState") or poll_data.get("state")
        if not state:
            return False
        status = self._map_api_state_to_status(str(state).upper(), device.status)
        return self.transition_device(device, status, metadata={"source": "poll"})

    def handle_missing_device(self, device: WirelessChassis | WirelessUnit) -> bool:
        """Mark device missing during poll as offline."""
        return self.transition_device(
            device, HardwareStatus.OFFLINE.value, reason="Missing in poll"
        )

    def get_state_history(self, device: WirelessChassis | WirelessUnit) -> None:
        """Placeholder for future state history backend."""
        return None

    # Helper methods

    def _is_valid_transition(self, from_status: str, to_status: str) -> bool:
        """Check if transition is valid."""
        if from_status == to_status:
            return True  # No-op transition
        return to_status in self.VALID_TRANSITIONS.get(from_status, [])

    def _map_api_state_to_status(self, api_state: str, current_status: str) -> str:
        """Map manufacturer API state to HardwareStatus."""
        return map_api_state_to_status(api_state, current_status)


def map_api_state_to_status(api_state: str, current_status: str) -> str:
    """Map manufacturer API state to HardwareStatus."""
    state_mapping = {
        "ONLINE": HardwareStatus.ONLINE.value,
        "DISCOVERING": HardwareStatus.PROVISIONING.value,
        "OFFLINE": HardwareStatus.OFFLINE.value,
        "UNKNOWN": HardwareStatus.DISCOVERED.value,
    }
    return state_mapping.get(api_state, current_status)


def get_structured_logger() -> Any:
    """Get structured logger instance."""
    from micboard.services.logging import get_structured_logger

    return get_structured_logger()


def get_lifecycle_manager(service_code: str | None = None) -> HardwareLifecycleManager:
    """Get device lifecycle manager instance."""
    return HardwareLifecycleManager(service_code=service_code)
