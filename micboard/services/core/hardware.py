"""Hardware service layer for managing chassis and field units.

Handles hardware lifecycle operations, status synchronization, and queries.
Consolidates logic from legacy device services.

This module is a facade - implementation is split across:
- hardware_query: read operations (get, search, count)
- hardware_sync: write operations (sync status, battery, channels, capabilities)
- hardware_post_save_hooks: save/delete side effects
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from micboard.services.core.hardware_post_save_hooks import HardwarePostSaveHooks
from micboard.services.core.hardware_query import HardwareQueryService
from micboard.services.core.hardware_sync import HardwareSyncService

if TYPE_CHECKING:  # pragma: no cover
    pass

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class NormalizedHardware:
    """Normalized hardware payload independent of manufacturer key names."""

    api_device_id: str
    ip: str
    serial_number: str
    mac_address: str
    name: str
    model: str
    device_type: str
    firmware_version: str
    hosted_firmware_version: str
    description: str
    subnet_mask: str | None
    gateway: str | None
    network_mode: str
    interface_id: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> NormalizedHardware | None:
        """Best-effort normalization for heterogeneous vendor payloads."""
        api_device_id = (data.get("id") or data.get("api_device_id") or "").strip()
        ip = (
            data.get("ip")
            or data.get("ipAddress")
            or data.get("ipv4")
            or data.get("ip_address")
            or ""
        ).strip()

        if not api_device_id or not ip:
            return None

        serial_number = (
            data.get("serial_number") or data.get("serialNumber") or data.get("serial") or ""
        ).strip()
        mac_address = (
            data.get("mac_address") or data.get("macAddress") or data.get("mac") or ""
        ).strip()

        return cls(
            api_device_id=api_device_id,
            ip=ip,
            serial_number=serial_number,
            mac_address=mac_address,
            name=(data.get("name") or data.get("model") or "").strip(),
            model=(data.get("model") or "").strip(),
            device_type=(data.get("device_type") or "").strip(),
            firmware_version=(
                data.get("firmware")
                or data.get("firmware_version")
                or data.get("firmwareVersion")
                or ""
            ).strip(),
            hosted_firmware_version=(data.get("hosted_firmware_version") or "").strip(),
            description=(data.get("description") or "").strip(),
            subnet_mask=data.get("subnet_mask") or data.get("subnetMask"),
            gateway=data.get("gateway"),
            network_mode=(data.get("network_mode") or data.get("networkMode") or "auto").strip(),
            interface_id=(data.get("interface_id") or data.get("interfaceId") or "").strip(),
        )


class HardwareService:
    """Business logic for hardware management and synchronization.

    Encapsulates operations on chassis, wireless units, and related logic.
    """

    # Query operations - delegated to HardwareQueryService
    get_active_chassis = HardwareQueryService.get_active_chassis
    get_active_units = HardwareQueryService.get_active_units
    get_chassis_by_ip = HardwareQueryService.get_chassis_by_ip
    get_chassis_by_id = HardwareQueryService.get_chassis_by_id
    get_unit_by_id = HardwareQueryService.get_unit_by_id
    count_online_hardware = HardwareQueryService.count_online_hardware
    search_hardware = HardwareQueryService.search_hardware

    # Sync operations - delegated to HardwareSyncService
    sync_hardware_status = HardwareSyncService.sync_hardware_status
    sync_unit_battery = HardwareSyncService.sync_unit_battery
    ensure_channel_count = HardwareSyncService.ensure_channel_count
    update_device_capabilities = HardwareSyncService.update_device_capabilities
    async_sync_hardware_status = HardwareSyncService.async_sync_hardware_status

    # Post-save hooks - delegated to HardwarePostSaveHooks
    handle_chassis_save = HardwarePostSaveHooks.handle_chassis_save
    handle_chassis_delete = HardwarePostSaveHooks.handle_chassis_delete

    # Async query operations - delegated to HardwareQueryService
    aget_active_chassis = HardwareQueryService.aget_active_chassis
    aget_online_chassis = HardwareQueryService.aget_online_chassis
    aget_chassis_by_id = HardwareQueryService.aget_chassis_by_id
    aget_active_units = HardwareQueryService.aget_active_units
    aget_unit_by_id = HardwareQueryService.aget_unit_by_id
    aget_low_battery_units = HardwareQueryService.aget_low_battery_units
