"""Post-save and post-delete hooks for chassis lifecycle.

Handles side effects that must occur after a chassis is saved or deleted:
- Auto-provisioning of RF channels to match model capacity
- Bi-directional sync: adding/removing IPs from manufacturer's discovery list
- Scheduling background discovery tasks
"""

from __future__ import annotations

import logging
from functools import partial

from django.conf import settings
from django.db import DEFAULT_DB_ALIAS, transaction

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.hardware.dtos import ChassisDiscoveryCleanup
from micboard.utils.dependencies import enqueue_huey_task, huey_is_configured

logger = logging.getLogger(__name__)


class HardwarePostSaveHooks:
    @staticmethod
    def handle_chassis_save(
        *,
        chassis: WirelessChassis,
        created: bool,
        using: str = "default",
    ) -> None:
        """Handle transactional and post-commit effects of saving a chassis."""
        HardwarePostSaveHooks._ensure_channel_count(chassis, using=using)

        if chassis.pk is None:  # pragma: no cover - save contract guard
            raise ValueError("A persisted chassis is required for post-save hooks.")
        transaction.on_commit(
            partial(
                HardwarePostSaveHooks._run_external_save_hooks,
                chassis_id=chassis.pk,
                created=created,
                using=using,
            ),
            using=using,
            robust=True,
        )

        if created:
            logger.info("Chassis created: %s at %s", chassis.name, chassis.ip)
        else:
            logger.debug("Chassis updated: %s", chassis.name)

    @staticmethod
    def _run_external_save_hooks(
        *,
        chassis_id: int,
        created: bool,
        using: str = "default",
    ) -> None:
        """Run manufacturer and task effects after durable persistence."""
        if getattr(settings, "TESTING", False):
            return
        chassis = (
            WirelessChassis.objects.using(using)
            .select_related("manufacturer")
            .filter(pk=chassis_id)
            .first()
        )
        if chassis is None:
            return
        if created:
            HardwarePostSaveHooks._add_ip_to_discovery(chassis)
        HardwarePostSaveHooks._schedule_discovery(chassis, using=using)

    @staticmethod
    def _ensure_channel_count(
        chassis: WirelessChassis,
        *,
        using: str = DEFAULT_DB_ALIAS,
    ) -> None:
        from micboard.services.core.hardware_sync import HardwareSyncService

        try:
            created_count, deleted_count = HardwareSyncService.ensure_channel_count(
                chassis=chassis,
                using=using,
            )
            if created_count > 0:
                logger.info(
                    "Auto-created %d RF channels for %s (%s)",
                    created_count,
                    chassis.name,
                    chassis.model,
                )
            if deleted_count > 0:
                logger.info(
                    "Auto-deleted %d excess RF channels for %s",
                    deleted_count,
                    chassis.name,
                )
        except Exception:
            logger.exception("Error ensuring channel count for chassis: %s", chassis.name)

    @staticmethod
    def _add_ip_to_discovery(chassis: WirelessChassis) -> None:
        if getattr(settings, "TESTING", False) or not chassis.ip or not chassis.manufacturer:
            return

        from micboard.services.manufacturer.plugin_registry import PluginRegistry

        try:
            plugin = PluginRegistry.get_plugin(chassis.manufacturer.code, chassis.manufacturer)
            if not plugin or not hasattr(plugin, "add_discovery_ips"):
                return
            success = plugin.add_discovery_ips([chassis.ip])
            if success:
                logger.info(
                    "Added %s to %s discovery list for automatic monitoring",
                    chassis.ip,
                    chassis.manufacturer.name,
                )
            else:
                logger.warning(
                    "Could not add %s to %s discovery list",
                    chassis.ip,
                    chassis.manufacturer.name,
                )
        except Exception:
            logger.exception(
                "Failed to add IP %s to discovery list for %s",
                chassis.ip,
                chassis.manufacturer.code,
            )

    @staticmethod
    def _schedule_discovery(chassis: WirelessChassis, *, using: str = "default") -> None:
        if getattr(settings, "TESTING", False) or not chassis.ip:
            return

        try:
            from micboard.tasks.sync.discovery import sync_receiver_discovery

            if huey_is_configured():
                enqueue_huey_task(sync_receiver_discovery, chassis.pk, using=using)
            else:
                sync_receiver_discovery(chassis.pk, using=using)
        except Exception:
            logger.exception("Failed to schedule discovery task")

    @staticmethod
    def handle_chassis_delete(
        *,
        chassis: WirelessChassis,
        using: str = "default",
    ) -> None:
        """Register manufacturer cleanup after one chassis deletion commits."""
        logger.info("Chassis deleted: %s (%s)", chassis.name, chassis.api_device_id)
        HardwarePostSaveHooks.handle_chassis_bulk_delete(
            chassis_list=[chassis],
            using=using,
        )

    @staticmethod
    def handle_chassis_bulk_delete(
        *,
        chassis_list: list[WirelessChassis],
        using: str = "default",
    ) -> None:
        """Register one grouped discovery cleanup for a chassis deletion batch."""
        targets = tuple(
            ChassisDiscoveryCleanup(
                manufacturer_id=chassis.manufacturer_id,
                ip=str(chassis.ip),
            )
            for chassis in chassis_list
            if chassis.ip and chassis.manufacturer_id is not None
        )
        if targets:
            transaction.on_commit(
                partial(
                    HardwarePostSaveHooks._remove_ips_from_discovery,
                    targets=targets,
                    using=using,
                ),
                using=using,
                robust=True,
            )

    @staticmethod
    def _remove_ips_from_discovery(
        *,
        targets: tuple[ChassisDiscoveryCleanup, ...],
        using: str = "default",
    ) -> None:
        """Remove committed chassis IPs from each manufacturer's discovery list."""
        if getattr(settings, "TESTING", False):
            return

        from micboard.models.discovery.manufacturer import Manufacturer
        from micboard.services.manufacturer.plugin_registry import PluginRegistry

        targets_by_manufacturer: dict[int, list[ChassisDiscoveryCleanup]] = {}
        for target in targets:
            targets_by_manufacturer.setdefault(target.manufacturer_id, []).append(target)

        for manufacturer_id, manufacturer_targets in targets_by_manufacturer.items():
            manufacturer = Manufacturer.objects.using(using).filter(pk=manufacturer_id).first()
            if manufacturer is None:
                continue
            ips = [target.ip for target in manufacturer_targets]
            try:
                plugin = PluginRegistry.get_plugin(manufacturer.code, manufacturer)

                if plugin and hasattr(plugin, "remove_discovery_ips"):
                    success = plugin.remove_discovery_ips(ips)
                    if success:
                        logger.info(
                            "Removed %s from %s discovery list",
                            ", ".join(ips),
                            manufacturer.name,
                        )
                    else:
                        logger.warning(
                            "Could not remove %s from %s discovery list",
                            ", ".join(ips),
                            manufacturer.name,
                        )
            except Exception:
                logger.exception(
                    "Failed to remove IPs %s from discovery list for %s",
                    ", ".join(ips),
                    manufacturer.code,
                )
