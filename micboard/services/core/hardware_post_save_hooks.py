"""Post-save and post-delete hooks for chassis lifecycle.

Handles side effects that must occur after a chassis is saved or deleted:
- Auto-provisioning of RF channels to match model capacity
- Bi-directional sync: adding/removing IPs from manufacturer's discovery list
- Scheduling background discovery tasks
"""

from __future__ import annotations

import logging

from django.conf import settings

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.utils.dependencies import enqueue_huey_task, huey_is_configured

logger = logging.getLogger(__name__)


class HardwarePostSaveHooks:
    @staticmethod
    def handle_chassis_save(*, chassis: WirelessChassis, created: bool) -> None:
        """Handle side effects of saving a chassis."""
        HardwarePostSaveHooks._ensure_channel_count(chassis)
        if created:
            HardwarePostSaveHooks._add_ip_to_discovery(chassis)
        HardwarePostSaveHooks._schedule_discovery(chassis)

        if created:
            logger.info("Chassis created: %s at %s", chassis.name, chassis.ip)
        else:
            logger.debug("Chassis updated: %s", chassis.name)

    @staticmethod
    def _ensure_channel_count(chassis: WirelessChassis) -> None:
        from micboard.services.core.hardware_sync import HardwareSyncService

        try:
            created_count, deleted_count = HardwareSyncService.ensure_channel_count(chassis=chassis)
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
        if not chassis.ip or not chassis.manufacturer:
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
    def _schedule_discovery(chassis: WirelessChassis) -> None:
        if getattr(settings, "TESTING", False) or not chassis.ip:
            return

        try:
            from micboard.tasks.sync.discovery import sync_receiver_discovery

            if huey_is_configured():
                enqueue_huey_task(sync_receiver_discovery, chassis.pk)
            else:
                sync_receiver_discovery(chassis.pk)
        except Exception:
            logger.exception("Failed to schedule discovery task")

    @staticmethod
    def handle_chassis_delete(*, chassis: WirelessChassis) -> None:
        """Handle side effects of deleting a chassis."""
        from micboard.services.manufacturer.plugin_registry import PluginRegistry

        logger.info("Chassis deleted: %s (%s)", chassis.name, chassis.api_device_id)

        # Bi-directional sync: Remove IP from manufacturer's discovery list
        if chassis.ip and chassis.manufacturer:
            try:
                plugin = PluginRegistry.get_plugin(chassis.manufacturer.code, chassis.manufacturer)

                if plugin and hasattr(plugin, "remove_discovery_ips"):
                    success = plugin.remove_discovery_ips([chassis.ip])
                    if success:
                        logger.info(
                            "Removed %s from %s discovery list",
                            chassis.ip,
                            chassis.manufacturer.name,
                        )
                    else:
                        logger.warning(
                            "Could not remove %s from %s discovery list",
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
