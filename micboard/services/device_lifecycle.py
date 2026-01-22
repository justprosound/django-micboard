"""
Device lifecycle management service.

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
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from micboard.models import Receiver, Transmitter

logger = logging.getLogger(__name__)


class DeviceStatus(str, Enum):
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
    def active_states(cls) -> List[str]:
        """States where device is considered active."""
        return [cls.ONLINE.value, cls.DEGRADED.value, cls.PROVISIONING.value]

    @classmethod
    def inactive_states(cls) -> List[str]:
        """States where device is considered inactive."""
        return [cls.OFFLINE.value, cls.MAINTENANCE.value, cls.RETIRED.value]


class DeviceLifecycleManager:
    """
    Centralized manager for device lifecycle operations.

    Handles:
    - State transitions with validation
    - Bi-directional sync with manufacturer APIs
    - Activity logging
    - Health monitoring
    
    Does NOT use signals for state management (signals only for broadcasts).
    """

    # Valid state transitions (from_state -> [to_states])
    VALID_TRANSITIONS: Dict[str, List[str]] = {
        DeviceStatus.DISCOVERED.value: [
            DeviceStatus.PROVISIONING.value,
            DeviceStatus.OFFLINE.value,
            DeviceStatus.RETIRED.value,
        ],
        DeviceStatus.PROVISIONING.value: [
            DeviceStatus.ONLINE.value,
            DeviceStatus.OFFLINE.value,
            DeviceStatus.DISCOVERED.value,
        ],
        DeviceStatus.ONLINE.value: [
            DeviceStatus.DEGRADED.value,
            DeviceStatus.OFFLINE.value,
            DeviceStatus.MAINTENANCE.value,
        ],
        DeviceStatus.DEGRADED.value: [
            DeviceStatus.ONLINE.value,
            DeviceStatus.OFFLINE.value,
            DeviceStatus.MAINTENANCE.value,
        ],
        DeviceStatus.OFFLINE.value: [
            DeviceStatus.ONLINE.value,
            DeviceStatus.DEGRADED.value,
            DeviceStatus.MAINTENANCE.value,
            DeviceStatus.RETIRED.value,
        ],
        DeviceStatus.MAINTENANCE.value: [
            DeviceStatus.ONLINE.value,
            DeviceStatus.OFFLINE.value,
            DeviceStatus.RETIRED.value,
        ],
        DeviceStatus.RETIRED.value: [],  # Terminal state
    }

    def __init__(self, service_code: Optional[str] = None):
        """
        Initialize lifecycle manager.

        Args:
            service_code: Optional manufacturer service code for logging context
        """
        self.service_code = service_code
        self._logger = get_structured_logger()

    @transaction.atomic
    def transition_device(
        self,
        device: Receiver | Transmitter,
        to_status: str,
        *,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        sync_to_api: bool = False,
    ) -> bool:
        """
        Transition device to new status with validation and logging.

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
        self, device: Receiver | Transmitter, *, device_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Mark device as discovered."""
        return self.transition_device(
            device,
            DeviceStatus.DISCOVERED.value,
            reason="Device discovered via API",
            metadata=device_data,
        )

    def mark_online(
        self, device: Receiver | Transmitter, *, health_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Mark device as online/operational."""
        return self.transition_device(
            device,
            DeviceStatus.ONLINE.value,
            reason="Device responding to polls",
            metadata=health_data,
        )

    def mark_degraded(
        self, device: Receiver | Transmitter, *, warnings: Optional[List[str]] = None
    ) -> bool:
        """Mark device as degraded (functional but with issues)."""
        return self.transition_device(
            device,
            DeviceStatus.DEGRADED.value,
            reason="Device has warnings or performance issues",
            metadata={"warnings": warnings or []},
        )

    def mark_offline(
        self, device: Receiver | Transmitter, *, reason: str = "Not responding"
    ) -> bool:
        """Mark device as offline."""
        return self.transition_device(
            device, DeviceStatus.OFFLINE.value, reason=reason
        )

    def mark_maintenance(
        self, device: Receiver | Transmitter, *, reason: str = "Administrative action"
    ) -> bool:
        """Mark device as in maintenance mode."""
        return self.transition_device(
            device,
            DeviceStatus.MAINTENANCE.value,
            reason=reason,
            sync_to_api=True,  # Push to API to disable alerts
        )

    def mark_retired(
        self, device: Receiver | Transmitter, *, reason: str = "Decommissioned"
    ) -> bool:
        """Mark device as retired (terminal state)."""
        return self.transition_device(
            device, DeviceStatus.RETIRED.value, reason=reason
        )

    @transaction.atomic
    def update_device_from_api(
        self,
        device: Receiver | Transmitter,
        api_data: Dict[str, Any],
        *,
        service_code: str,
    ) -> bool:
        """
        Update device from manufacturer API data (pull sync).

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

        device.save(
            update_fields=["name", "firmware_version", "status", "last_seen", "updated_at"]
        )

        # Log update
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
        device: Receiver | Transmitter,
        service,
        *,
        fields: Optional[List[str]] = None,
    ) -> bool:
        """
        Push device changes to manufacturer API (push sync).

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
        self, device: Receiver | Transmitter, *, threshold_minutes: int = 5
    ) -> str:
        """
        Check device health and auto-transition if needed.

        Args:
            device: Device to check
            threshold_minutes: Minutes without response before marking offline

        Returns:
            Current health status
        """
        if device.status == DeviceStatus.MAINTENANCE.value:
            return "maintenance"

        if device.status == DeviceStatus.RETIRED.value:
            return "retired"

        if not device.last_seen:
            # Never seen, leave in current state
            return "unknown"

        time_since = timezone.now() - device.last_seen
        threshold = timedelta(minutes=threshold_minutes)

        if time_since > threshold:
            # Auto-transition to offline
            if device.status != DeviceStatus.OFFLINE.value:
                self.mark_offline(
                    device, reason=f"No response for {time_since.total_seconds():.0f}s"
                )
            return "offline"

        # Device is responsive
        if device.status == DeviceStatus.OFFLINE.value:
            # Auto-recover to online
            self.mark_online(device)

        return device.status

    def bulk_health_check(
        self,
        devices: List[Receiver | Transmitter],
        *,
        threshold_minutes: int = 5,
    ) -> Dict[str, int]:
        """
        Check health of multiple devices efficiently.

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

    # Helper methods

    def _is_valid_transition(self, from_status: str, to_status: str) -> bool:
        """Check if transition is valid."""
        if from_status == to_status:
            return True  # No-op transition
        return to_status in self.VALID_TRANSITIONS.get(from_status, [])

    def _map_api_state_to_status(self, api_state: str, current_status: str) -> str:
        """Map manufacturer API state to DeviceStatus."""
        state_mapping = {
            "ONLINE": DeviceStatus.ONLINE.value,
            "DISCOVERING": DeviceStatus.PROVISIONING.value,
            "OFFLINE": DeviceStatus.OFFLINE.value,
            "UNKNOWN": DeviceStatus.DISCOVERED.value,
        }
        return state_mapping.get(api_state, current_status)

    def _build_api_payload(
        self, device: Receiver | Transmitter, fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Build API payload from device model."""
        payload = {
            "name": device.name,
            "status": device.status,
        }

        if fields:
            payload = {k: v for k, v in payload.items() if k in fields}

        return payload

    def _sync_status_to_api(
        self, device: Receiver | Transmitter, status: str, metadata: Optional[Dict[str, Any]]
    ) -> None:
        """Push status change to manufacturer API."""
        if not self.service_code:
            return

        try:
            from micboard.services.manufacturer_service import get_service

            service = get_service(self.service_code)
            if service:
                self.sync_device_to_api(device, service, fields=["status"])
        except Exception as e:
            logger.warning(
                f"Failed to sync status to API: {e}",
                exc_info=True,
                extra={"device_id": device.pk, "status": status},
            )


def get_structured_logger():
    """Get structured logger instance."""
    from micboard.services.logging import get_structured_logger

    return get_structured_logger()


def get_lifecycle_manager(service_code: Optional[str] = None) -> DeviceLifecycleManager:
    """Get device lifecycle manager instance."""
    return DeviceLifecycleManager(service_code=service_code)
