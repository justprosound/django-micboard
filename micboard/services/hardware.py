"""Hardware service layer for managing chassis and field units.

Handles hardware lifecycle operations, status synchronization, and queries.
Consolidates logic from legacy device services.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from django.db import models
from django.db.models import QuerySet

from micboard.models import WirelessChassis, WirelessUnit
from micboard.services.tenant_filters import apply_tenant_filters

if TYPE_CHECKING:  # pragma: no cover
    pass

logger = logging.getLogger(__name__)
_ModelT = TypeVar("_ModelT", bound=models.Model)


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

    @staticmethod
    def get_active_chassis(
        *,
        organization_id: int | None = None,
        site_id: int | None = None,
        campus_id: int | None = None,
    ) -> QuerySet[WirelessChassis]:
        """Fetch all active chassis."""
        qs: QuerySet[WirelessChassis] = WirelessChassis.objects.active()
        return apply_tenant_filters(
            qs,
            organization_id=organization_id,
            campus_id=campus_id,
            site_id=site_id,
            building_path="location__building",
        )

    @staticmethod
    def get_active_units(
        *,
        organization_id: int | None = None,
        site_id: int | None = None,
        campus_id: int | None = None,
    ) -> QuerySet[WirelessUnit]:
        """Fetch all active field units."""
        qs: QuerySet[WirelessUnit] = WirelessUnit.objects.active()
        return apply_tenant_filters(
            qs,
            organization_id=organization_id,
            campus_id=campus_id,
            site_id=site_id,
            building_path="base_chassis__location__building",
        )

    @staticmethod
    def get_chassis_by_ip(*, ip: str) -> WirelessChassis | None:
        """Find a chassis by IP address."""
        return WirelessChassis.objects.filter(ip=ip).first()

    @staticmethod
    def get_chassis_by_id(*, chassis_id: int) -> WirelessChassis:
        """Get a chassis by its ID."""
        from micboard.services.exceptions import HardwareNotFoundError

        try:
            return WirelessChassis.objects.get(id=chassis_id)
        except WirelessChassis.DoesNotExist:
            raise HardwareNotFoundError(f"Chassis with ID {chassis_id} not found") from None

    @staticmethod
    def get_unit_by_id(*, unit_id: int) -> WirelessUnit:
        """Get a wireless unit by its ID."""
        from micboard.services.exceptions import HardwareNotFoundError

        try:
            return WirelessUnit.objects.get(id=unit_id)
        except WirelessUnit.DoesNotExist:
            raise HardwareNotFoundError(f"Wireless unit with ID {unit_id} not found") from None

    @staticmethod
    def sync_hardware_status(*, obj: WirelessChassis | WirelessUnit, online: bool) -> None:
        """Update hardware online status."""
        from micboard.services.hardware_lifecycle import get_lifecycle_manager

        if isinstance(obj, WirelessChassis):
            lifecycle = get_lifecycle_manager(obj.manufacturer.code)
            if online:
                lifecycle.mark_online(obj)
            else:
                lifecycle.mark_offline(obj)
        elif isinstance(obj, WirelessUnit):
            obj.status = "online" if online else "offline"
            obj.save(update_fields=["status"])

    @staticmethod
    def sync_unit_battery(*, unit: WirelessUnit, battery_level: int) -> None:
        """Update field unit battery level."""
        if not (0 <= battery_level <= 255):
            raise ValueError("battery_level must be 0-255")

        if unit.battery != battery_level:
            unit.battery = battery_level
            unit.save(update_fields=["battery", "updated_at"])

    @staticmethod
    def count_online_hardware() -> dict[str, int]:
        """Get count of online hardware by type."""
        return {
            "chassis": WirelessChassis.objects.filter(is_online=True).count(),
            "units": WirelessUnit.objects.filter(status="online").count(),
        }

    @staticmethod
    def search_hardware(*, query: str) -> list[WirelessChassis | WirelessUnit]:
        """Search hardware by name, IP, or serial number."""
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
    def handle_chassis_save(*, chassis: WirelessChassis, created: bool) -> None:
        """Handle side effects of saving a chassis."""
        import logging

        from django.conf import settings

        from micboard.tasks.discovery_tasks import sync_receiver_discovery
        from micboard.utils.dependencies import HAS_DJANGO_Q

        logger = logging.getLogger(__name__)

        # 1. Ensure channels match model capacity
        try:
            created_count, deleted_count = chassis.ensure_channel_count()
            if created_count > 0:
                logger.info(
                    "Auto-created %d RF channels for %s (%s)",
                    created_count,
                    chassis.name,
                    chassis.model,
                )
            if deleted_count > 0:
                logger.info(
                    "Auto-deleted %d excess RF channels for %s", deleted_count, chassis.name
                )
        except Exception:
            logger.exception("Error ensuring channel count for chassis: %s", chassis.name)

        # 2. Bi-directional sync: Add IP to manufacturer's discovery list
        if chassis.ip and chassis.manufacturer and created:
            try:
                from micboard.services.plugin_registry import PluginRegistry

                plugin = PluginRegistry.get_plugin(chassis.manufacturer.code, chassis.manufacturer)

                # Check if plugin supports discovery IP management
                if plugin and hasattr(plugin, "add_discovery_ips"):
                    success = plugin.add_discovery_ips([chassis.ip])
                    if success:
                        logger.info(
                            "✅ Added %s to %s discovery list for automatic monitoring",
                            chassis.ip,
                            chassis.manufacturer.name,
                        )
                    else:
                        logger.warning(
                            "⚠️ Could not add %s to %s discovery list",
                            chassis.ip,
                            chassis.manufacturer.name,
                        )
            except Exception as e:
                logger.warning(
                    "Failed to add IP %s to discovery list for %s: %s",
                    chassis.ip,
                    chassis.manufacturer.code,
                    e,
                )

        # 3. Schedule discovery sync
        if not getattr(settings, "TESTING", False) and chassis.ip:
            if HAS_DJANGO_Q:
                try:
                    from django_q.tasks import async_task

                    async_task(sync_receiver_discovery, chassis.pk)
                except Exception:
                    logger.exception("Failed to schedule discovery task")
            else:
                try:
                    sync_receiver_discovery(chassis.pk)
                except Exception:
                    logger.exception("Failed to run discovery synchronously")

        if created:
            logger.info("Chassis created: %s at %s", chassis.name, chassis.ip)
        else:
            logger.debug("Chassis updated: %s", chassis.name)

    @staticmethod
    def handle_chassis_delete(*, chassis: WirelessChassis) -> None:
        """Handle side effects of deleting a chassis."""
        import logging

        logger = logging.getLogger(__name__)
        logger.info("Chassis deleted: %s (%s)", chassis.name, chassis.api_device_id)

        # Bi-directional sync: Remove IP from manufacturer's discovery list
        if chassis.ip and chassis.manufacturer:
            try:
                from micboard.services.plugin_registry import PluginRegistry

                plugin = PluginRegistry.get_plugin(chassis.manufacturer.code, chassis.manufacturer)

                # Check if plugin supports discovery IP management
                if plugin and hasattr(plugin, "remove_discovery_ips"):
                    success = plugin.remove_discovery_ips([chassis.ip])
                    if success:
                        logger.info(
                            "✅ Removed %s from %s discovery list",
                            chassis.ip,
                            chassis.manufacturer.name,
                        )
                    else:
                        logger.warning(
                            "⚠️ Could not remove %s from %s discovery list",
                            chassis.ip,
                            chassis.manufacturer.name,
                        )
            except Exception as e:
                logger.warning(
                    "Failed to remove IP %s from discovery list for %s: %s",
                    chassis.ip,
                    chassis.manufacturer.code,
                    e,
                )
