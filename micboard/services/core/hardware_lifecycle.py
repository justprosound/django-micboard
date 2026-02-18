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

        # Optionally sync to manufacturer API
        if sync_to_api and self.service_code:
            self._sync_status_to_api(device, to_status, metadata)

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

    @transaction.atomic
    def update_device_from_api(
        self,
        device: WirelessChassis | WirelessUnit,
        api_data: dict[str, Any],
        *,
        service_code: str,
    ) -> bool:
        """Update device from manufacturer API data (pull sync).

        Args:
            device: Device to update
            api_data: Raw data from manufacturer API
            service_code: Manufacturer service code

        Returns:
            True if update succeeded
        """
        device = device.__class__.objects.select_for_update().get(pk=device.pk)

        old_values = {
            "name": device.name,
            "firmware_version": device.firmware_version,
            "status": device.status,
        }

        # Update fields from API
        device.name = api_data.get("name", device.name)
        device.firmware_version = api_data.get("firmware_version", device.firmware_version)
        device.last_seen = timezone.now()

        # Determine status from API state
        api_state = api_data.get("state", "").upper()
        new_status = self._map_api_state_to_status(api_state, device.status)

        if new_status != device.status:
            device.status = new_status

        device.save(update_fields=["name", "firmware_version", "status", "last_seen", "updated_at"])

        # Log update
        if self._logger:
            self._logger.log_crud_update(
                device,
                old_values=old_values,
                new_values={
                    "name": device.name,
                    "firmware_version": device.firmware_version,
                    "status": device.status,
                },
            )

        logger.debug(
            f"Updated device from API: {device.__class__.__name__} {device.pk}",
            extra={
                "device_id": device.pk,
                "service_code": service_code,
                "api_data_keys": list(api_data.keys()),
            },
        )

        return True

    def sync_device_to_api(
        self,
        device: WirelessChassis | WirelessUnit,
        service,
        *,
        fields: list[str] | None = None,
    ) -> bool:
        """Push device changes to manufacturer API (push sync).

        Args:
            device: Device to sync
            service: ManufacturerService instance
            fields: Optional list of fields to sync (None = all)

        Returns:
            True if sync succeeded
        """
        try:
            client = service.get_client()
            if not client:
                logger.error(f"No client available for {service.code}")
                return False

            # Build payload from device
            payload = self._build_api_payload(device, fields)

            # Push to API
            success = client.update_device(device.api_device_id, payload)

            if success:
                logger.info(
                    f"Synced device to API: {device.__class__.__name__} {device.pk}",
                    extra={
                        "device_id": device.pk,
                        "service_code": service.code,
                        "fields": fields or "all",
                    },
                )
            else:
                logger.warning(
                    f"Failed to sync device to API: {device.__class__.__name__} {device.pk}",
                    extra={"device_id": device.pk, "service_code": service.code},
                )

            return success

        except Exception as e:
            logger.error(
                f"Error syncing device to API: {e}",
                exc_info=True,
                extra={"device_id": device.pk},
            )
            return False

    def check_device_health(
        self, device: WirelessChassis | WirelessUnit, *, threshold_minutes: int = 5
    ) -> str:
        """Check device health and auto-transition if needed.

        Args:
            device: Device to check
            threshold_minutes: Minutes without response before marking offline

        Returns:
            Current health status
        """
        if device.status == HardwareStatus.MAINTENANCE.value:
            return "maintenance"

        if device.status == HardwareStatus.RETIRED.value:
            return "retired"

        if not device.last_seen:
            # Never seen, leave in current state
            return "unknown"

        time_since = timezone.now() - device.last_seen
        threshold = timedelta(minutes=threshold_minutes)

        if time_since > threshold:
            # Auto-transition to offline
            if device.status != HardwareStatus.OFFLINE.value:
                self.mark_offline(
                    device, reason=f"No response for {time_since.total_seconds():.0f}s"
                )
            return "offline"

        # Device is responsive
        if device.status == HardwareStatus.OFFLINE.value:
            # Auto-recover to online
            self.mark_online(device)

        return device.status

    def bulk_health_check(
        self,
        devices: list[WirelessChassis | WirelessUnit],
        *,
        threshold_minutes: int = 5,
    ) -> dict[str, int]:
        """Check health of multiple devices efficiently.

        Args:
            devices: List of devices to check
            threshold_minutes: Offline threshold

        Returns:
            Dict with status counts
        """
        results = {"online": 0, "offline": 0, "degraded": 0, "maintenance": 0, "other": 0}

        for device in devices:
            status = self.check_device_health(device, threshold_minutes=threshold_minutes)
            if status in results:
                results[status] += 1
            else:
                results["other"] += 1

        logger.info(
            f"Bulk health check: {len(devices)} devices",
            extra={"device_count": len(devices), "results": results},
        )

        return results

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

    def sync_state_from_api(
        self, device: WirelessChassis | WirelessUnit, api_data: dict[str, Any]
    ) -> bool:
        """Update a device's status field based on API payload."""
        state = api_data.get("deviceState") or api_data.get("state")
        if not state:
            return False
        target_status = self._map_api_state_to_status(str(state).upper(), device.status)
        return self.transition_device(device, target_status, metadata={"source": "api"})

    def bulk_mark_offline(self, *, chassis_ids: list[int]) -> int:
        """Mark multiple chassis offline."""
        from micboard.models import WirelessChassis

        updated = 0
        for chassis in WirelessChassis.objects.filter(pk__in=chassis_ids):
            if self.mark_offline(chassis, reason="Bulk offline operation"):
                updated += 1
        return updated

    def bulk_sync_states(self, api_states: dict[str, dict[str, Any]]) -> int:
        """Sync state for chassis keyed by serial_number."""
        from micboard.models import WirelessChassis

        serials = list(api_states.keys())
        updated = 0

        for chassis in WirelessChassis.objects.filter(serial_number__in=serials):
            payload = api_states.get(chassis.serial_number, {})
            if self.sync_state_from_api(chassis, payload):
                updated += 1

        return updated

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
        state_mapping = {
            "ONLINE": HardwareStatus.ONLINE.value,
            "DISCOVERING": HardwareStatus.PROVISIONING.value,
            "OFFLINE": HardwareStatus.OFFLINE.value,
            "UNKNOWN": HardwareStatus.DISCOVERED.value,
        }
        return state_mapping.get(api_state, current_status)

    def _build_api_payload(
        self, device: WirelessChassis | WirelessUnit, fields: list[str] | None = None
    ) -> dict[str, Any]:
        """Build API payload from device model."""
        payload = {
            "name": device.name,
            "status": device.status,
        }

        if fields:
            payload = {k: v for k, v in payload.items() if k in fields}

        return payload

    def _sync_status_to_api(
        self,
        device: WirelessChassis | WirelessUnit,
        status: str,
        metadata: dict[str, Any] | None,
    ) -> None:
        """Push status change to manufacturer API."""
        if not self.service_code:
            return

        try:
            from micboard.services.manufacturer.plugin_registry import PluginRegistry

            plugin = PluginRegistry.get_plugin(self.service_code)
            if plugin:
                # Plugin found - log intent to sync
                # Note: Actual sync implementation is manufacturer-specific
                logger.info(
                    f"Plugin available for {self.service_code}, "
                    f"status sync may require manufacturer-specific implementation",
                    extra={"device_id": device.pk, "status": status},
                )
        except Exception as e:
            logger.warning(
                f"Failed to sync status to API: {e}",
                exc_info=True,
                extra={"device_id": device.pk, "status": status},
            )


def get_structured_logger() -> Any:
    """Get structured logger instance."""
    from micboard.services.logging import get_structured_logger

    return get_structured_logger()


def get_lifecycle_manager(service_code: str | None = None) -> HardwareLifecycleManager:
    """Get device lifecycle manager instance."""
    return HardwareLifecycleManager(service_code=service_code)
