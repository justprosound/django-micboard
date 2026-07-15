"""Post-save and post-delete hooks for chassis lifecycle.

Handles side effects that must occur after a chassis is saved or deleted:
- Auto-provisioning of RF channels to match model capacity
- Removing deleted IPs from manufacturer discovery lists
"""

from __future__ import annotations

import logging

from django.db import DEFAULT_DB_ALIAS

from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.utils.exception_logging import sanitized_exception_info

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

        if created:
            logger.info(
                "Wireless chassis %s created for manufacturer %s",
                chassis.pk,
                chassis.manufacturer_id,
            )
        else:
            logger.debug("Wireless chassis %s updated", chassis.pk)

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
                    "Auto-created %d RF channels for wireless chassis %s",
                    created_count,
                    chassis.pk,
                )
            if deleted_count > 0:
                logger.info(
                    "Auto-deleted %d excess RF channels for wireless chassis %s",
                    deleted_count,
                    chassis.pk,
                )
        except Exception as exc:
            logger.exception(
                "Error ensuring channel count for chassis %s",
                chassis.pk,
                exc_info=sanitized_exception_info(exc),
            )

    @staticmethod
    def handle_chassis_delete(
        *,
        chassis: WirelessChassis,
        using: str = "default",
    ) -> None:
        """Register manufacturer reconciliation after one chassis deletion commits."""
        logger.info(
            "Wireless chassis %s deleted for manufacturer %s",
            chassis.pk,
            chassis.manufacturer_id,
        )
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
        """Register one claimed discovery reconciliation per affected manufacturer."""
        from micboard.services.sync.discovery_trigger_service import schedule_discovery_on_commit

        manufacturer_ids = sorted(
            {
                chassis.manufacturer_id
                for chassis in chassis_list
                if chassis.manufacturer_id is not None
            }
        )
        for manufacturer_id in manufacturer_ids:
            schedule_discovery_on_commit(
                manufacturer_id=manufacturer_id,
                scan_cidrs=False,
                scan_fqdns=False,
                using=using,
            )
