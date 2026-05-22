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

logger = logging.getLogger(__name__)


class HardwarePostSaveHooks:
    @staticmethod
    def handle_chassis_save(*, chassis: WirelessChassis, created: bool) -> None:
        """Handle side effects of saving a chassis."""
        from micboard.services.core.hardware_sync import HardwareSyncService
        from micboard.services.manufacturer.plugin_registry import PluginRegistry
        from micboard.tasks.sync.discovery import sync_receiver_discovery
        from micboard.utils.dependencies import HAS_DJANGO_Q

        # 1. Ensure channels match model capacity
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

        # 2. Bi-directional sync: Add IP to manufacturer's discovery list
        if chassis.ip and chassis.manufacturer and created:
            try:
                plugin = PluginRegistry.get_plugin(chassis.manufacturer.code, chassis.manufacturer)

                if plugin and hasattr(plugin, "add_discovery_ips"):
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
