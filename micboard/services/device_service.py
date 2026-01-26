"""Device management service for django-micboard.

Handles device lifecycle operations (CRUD, state management, synchronization)
across all manufacturers. Separates business logic from HTTP clients.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.db import models
from django.db.models import QuerySet

if TYPE_CHECKING:
    from micboard.models import WirelessChassis, WirelessUnit

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class NormalizedDevice:
    """Normalized device payload independent of manufacturer key names."""

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
    def from_api(cls, data: dict[str, Any]) -> NormalizedDevice | None:
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


class DeviceService:
    """Service for managing device lifecycle operations.

    Provides high-level API for device queries, state management,
    and data enrichment. All operations are manufacturer-agnostic.
    """

    @staticmethod
    def get_active_receivers() -> QuerySet[WirelessChassis]:
        """Fetch all chassis currently in active states."""
        from micboard.models import WirelessChassis

        return WirelessChassis.objects.active()

    @staticmethod
    def get_active_transmitters() -> QuerySet[WirelessUnit]:
        """Fetch all field units currently in active states."""
        from micboard.models import WirelessUnit

        return WirelessUnit.objects.active()

    @staticmethod
    def get_device_by_ip(*, ip: str) -> WirelessChassis | None:
        """Find a chassis by IP address."""
        from micboard.models import WirelessChassis

        return WirelessChassis.objects.filter(ip=ip).first()

    @staticmethod
    def get_receiver_by_id(*, receiver_id: int) -> WirelessChassis | None:
        """Get a chassis by its database ID."""
        from micboard.models import WirelessChassis

        try:
            return WirelessChassis.objects.get(id=receiver_id)
        except WirelessChassis.DoesNotExist:
            return None

    @staticmethod
    def get_transmitter_by_id(*, transmitter_id: int) -> WirelessUnit | None:
        """Get a field unit by its database ID."""
        from micboard.models import WirelessUnit

        try:
            return WirelessUnit.objects.get(id=transmitter_id)
        except WirelessUnit.DoesNotExist:
            return None

    @staticmethod
    def get_online_receivers() -> QuerySet[WirelessChassis]:
        """Get all chassis that are currently online."""
        from micboard.models import WirelessChassis

        return WirelessChassis.objects.filter(is_online=True)

    @staticmethod
    def get_offline_receivers() -> QuerySet[WirelessChassis]:
        """Get all chassis that are currently offline."""
        from micboard.models import WirelessChassis

        return WirelessChassis.objects.filter(is_online=False)

    @staticmethod
    def get_low_battery_receivers(*, threshold: int = 25) -> QuerySet[WirelessChassis]:
        """Get chassis with units having low battery levels."""
        from micboard.models import WirelessChassis

        return WirelessChassis.objects.filter(field_units__battery__lt=threshold).distinct()

    @staticmethod
    def count_active_receivers() -> int:
        """Count all active chassis."""
        return DeviceService.get_active_receivers().count()

    @staticmethod
    def count_online_receivers() -> int:
        """Count all online chassis."""
        return DeviceService.get_online_receivers().count()

    @staticmethod
    def count_offline_receivers() -> int:
        """Count all offline chassis."""
        return DeviceService.get_offline_receivers().count()

    @staticmethod
    def get_device_by_name(*, name: str) -> WirelessChassis | WirelessUnit | None:
        """Find a device by name."""
        from micboard.models import WirelessChassis, WirelessUnit

        # Check chassis first
        chassis = WirelessChassis.objects.filter(name__iexact=name).first()
        if chassis:
            return chassis

        # Check units
        unit = WirelessUnit.objects.filter(name__iexact=name).first()
        if unit:
            return unit

        return None

    @staticmethod
    def get_devices_in_location(*, location_id: int) -> QuerySet[WirelessChassis]:
        """Get all chassis assigned to a specific location."""
        from micboard.models import WirelessChassis

        return WirelessChassis.objects.filter(location_id=location_id)

    @staticmethod
    def search_devices(*, query: str) -> list[WirelessChassis | WirelessUnit]:
        """Search devices by name, IP, or serial number."""
        from micboard.models import WirelessChassis, WirelessUnit

        results = []

        # Search chassis
        chassis = WirelessChassis.objects.filter(
            models.Q(name__icontains=query)
            | models.Q(ip__icontains=query)
            | models.Q(serial_number__icontains=query)
        )
        results.extend(list(chassis))

        # Search units
        units = WirelessUnit.objects.filter(
            models.Q(name__icontains=query)
            | models.Q(frequency__icontains=query)
            | models.Q(serial_number__icontains=query)
        )
        results.extend(list(units))

        return results

    @staticmethod
    def sync_device_status(*, device_obj: WirelessChassis | WirelessUnit, online: bool) -> None:
        """Update the online status of a device."""
        from micboard.services.device_lifecycle import get_lifecycle_manager

        if isinstance(device_obj, WirelessChassis):
            lifecycle = get_lifecycle_manager(device_obj.manufacturer.code)
            if online:
                lifecycle.mark_online(device_obj)
            else:
                lifecycle.mark_offline(device_obj)
        elif isinstance(device_obj, WirelessUnit):
            device_obj.status = "online" if online else "offline"
            device_obj.save(update_fields=["status"])

    @staticmethod
    def sync_device_battery(*, device_obj: WirelessUnit, battery_level: int) -> None:
        """Update the battery level of a field unit."""
        if not (0 <= battery_level <= 255):
            raise ValueError("battery_level must be 0-255")

        device_obj.battery = battery_level
        device_obj.save(update_fields=["battery"])

    @staticmethod
    def mark_device_inactive(*, device_obj: WirelessChassis | WirelessUnit) -> None:
        """Mark a device as inactive."""
        from micboard.services.device_lifecycle import get_lifecycle_manager

        if isinstance(device_obj, WirelessChassis):
            lifecycle = get_lifecycle_manager(device_obj.manufacturer.code)
            lifecycle.mark_offline(device_obj)
        elif isinstance(device_obj, WirelessUnit):
            device_obj.status = "offline"
            device_obj.save(update_fields=["status"])

    @staticmethod
    def count_manufacturer_devices(*, manufacturer_code: str) -> dict[str, int]:
        """Count devices for a specific manufacturer."""
        from micboard.models import Manufacturer, WirelessChassis, WirelessUnit

        try:
            manufacturer = Manufacturer.objects.get(code=manufacturer_code)
        except Manufacturer.DoesNotExist:
            return {"chassis": 0, "units": 0}

        chassis_count = WirelessChassis.objects.filter(manufacturer=manufacturer).count()
        units_count = WirelessUnit.objects.filter(manufacturer=manufacturer).count()

        return {
            "chassis": chassis_count,
            "units": units_count,
        }
