"""Device API sync service for bi-directional manufacturer API synchronization."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from .hardware_lifecycle import (
    HardwareLifecycleManager,
    map_api_state_to_status,
)

if TYPE_CHECKING:
    from micboard.models.hardware.wireless_chassis import WirelessChassis
    from micboard.models.hardware.wireless_unit import WirelessUnit

logger = logging.getLogger(__name__)


def build_api_payload(
    device: WirelessChassis | WirelessUnit,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    """Build API payload from device model.

    Args:
        device: Device to build payload from
        fields: Optional list of fields to include (None = all)

    Returns:
        Payload dict for manufacturer API
    """
    payload: dict[str, Any] = {
        "name": device.name,
        "status": device.status,
    }
    if fields:
        payload = {k: v for k, v in payload.items() if k in fields}
    return payload


class DeviceAPISyncService:
    """Service for bi-directional sync between device models and manufacturer APIs.

    Handles pulling updates from APIs (update_from_api) and pushing
    local changes to APIs (sync_to_api). Requires a HardwareLifecycleManager
    for state transition delegation.
    """

    def __init__(
        self,
        lifecycle_manager: HardwareLifecycleManager,
        service_code: str | None = None,
    ):
        """Initialize API sync service.

        Args:
            lifecycle_manager: HardwareLifecycleManager for state transitions
            service_code: Optional manufacturer service code for context
        """
        self._lifecycle_manager = lifecycle_manager
        self.service_code = service_code

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

        device.name = api_data.get("name", device.name)
        device.firmware_version = api_data.get("firmware_version", device.firmware_version)
        device.last_seen = timezone.now()

        api_state = api_data.get("state", "").upper()
        new_status = map_api_state_to_status(api_state, device.status)

        if new_status != device.status:
            device.status = new_status

        update_fields = ["name", "firmware_version", "status", "last_seen"]
        if any(
            field.name == "updated_at" and field.concrete for field in device._meta.get_fields()
        ):
            update_fields.append("updated_at")
        device.save(update_fields=update_fields)

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
        service: Any,
        *,
        fields: list[str] | None = None,
    ) -> bool:
        """Push device changes to manufacturer API (push sync).

        Args:
            device: Device to sync
            service: Manufacturer plugin or API service instance
            fields: Optional list of fields to sync (None = all)

        Returns:
            True if sync succeeded
        """
        try:
            client = service.get_client()
            if not client:
                logger.error("No client available for %s", service.code)
                return False

            payload = build_api_payload(device, fields)

            device_id = getattr(device, "api_device_id", None) or device.pk
            success = client.update_device(device_id, payload)

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

    def sync_state_from_api(
        self,
        device: WirelessChassis | WirelessUnit,
        api_data: dict[str, Any],
    ) -> bool:
        """Update a device's status field based on API payload.

        Args:
            device: Device to update
            api_data: Raw data from manufacturer API

        Returns:
            True if status was updated
        """
        state = api_data.get("deviceState") or api_data.get("state")
        if not state:
            return False
        target_status = map_api_state_to_status(str(state).upper(), device.status)
        return self._lifecycle_manager.transition_device(
            device, target_status, metadata={"source": "api"}
        )

    def bulk_sync_states(self, api_states: dict[str, dict[str, Any]]) -> int:
        """Sync state for chassis keyed by serial_number.

        Args:
            api_states: Dict mapping serial_number to API payload

        Returns:
            Count of successfully synced chassis
        """
        from micboard.models.hardware.wireless_chassis import WirelessChassis

        serials = list(api_states.keys())
        updated = 0

        for chassis in WirelessChassis.objects.filter(serial_number__in=serials):
            payload = api_states.get(chassis.serial_number, {})
            if self.sync_state_from_api(chassis, payload):
                updated += 1

        return updated

    def bulk_mark_offline(self, *, chassis_ids: list[int]) -> int:
        """Mark multiple chassis offline.

        Args:
            chassis_ids: List of chassis primary keys to mark offline

        Returns:
            Count of successfully marked chassis
        """
        from micboard.models.hardware.wireless_chassis import WirelessChassis

        updated = 0
        for chassis in WirelessChassis.objects.filter(pk__in=chassis_ids):
            if self._lifecycle_manager.mark_offline(chassis, reason="Bulk offline operation"):
                updated += 1
        return updated
