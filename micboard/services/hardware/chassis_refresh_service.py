"""Tenant-preserving refresh workflow for selected wireless chassis."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.db import DEFAULT_DB_ALIAS, transaction
from django.utils import timezone

from micboard.services.hardware.dtos import ChassisRefreshResult

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from micboard.models.hardware.wireless_chassis import WirelessChassis

logger = logging.getLogger(__name__)


class ChassisRefreshService:
    """Refresh only the chassis explicitly present in a caller-scoped queryset."""

    @classmethod
    def _refresh_chassis(cls, chassis: WirelessChassis) -> bool:
        """Fetch one chassis outside a transaction, then persist atomically."""
        from micboard.services.manufacturer.plugin_registry import PluginRegistry

        plugin_class = PluginRegistry.get_plugin_class(chassis.manufacturer.code)
        plugin = plugin_class(chassis.manufacturer)
        device_data = plugin.get_device(chassis.api_device_id)
        if not device_data:
            return False

        transformed_data: dict[str, Any] | None = plugin.transform_device_data(device_data)
        if not transformed_data:
            return False

        return cls._apply_refresh(
            chassis_id=chassis.pk,
            transformed_data=transformed_data,
            using=chassis._state.db or DEFAULT_DB_ALIAS,
        )

    @staticmethod
    def _apply_refresh(
        *,
        chassis_id: int,
        transformed_data: dict[str, Any],
        using: str,
    ) -> bool:
        """Persist fetched details and lifecycle changes in one short transaction."""
        from micboard.models.hardware.wireless_chassis import WirelessChassis

        with transaction.atomic(using=using):
            chassis = (
                WirelessChassis._default_manager.using(using)
                .select_for_update()
                .select_related("manufacturer")
                .get(pk=chassis_id)
            )

            update_fields = {"last_seen"}
            chassis.last_seen = timezone.now()
            if name := transformed_data.get("name"):
                chassis.name = str(name)
                update_fields.add("name")
            if firmware := (
                transformed_data.get("firmware") or transformed_data.get("firmware_version")
            ):
                chassis.firmware_version = str(firmware)
                update_fields.add("firmware_version")
            chassis.save(update_fields=update_fields, using=using)

            if chassis.status == "retired":
                return True

            from micboard.services.core.hardware_lifecycle import get_lifecycle_manager

            lifecycle = get_lifecycle_manager(chassis.manufacturer.code)
            if chassis.status == "discovered":
                lifecycle.transition_device(
                    chassis,
                    "provisioning",
                    reason="Selected chassis refreshed from manufacturer API",
                )
            lifecycle.mark_online(chassis, health_data=transformed_data)
        return True

    @classmethod
    def refresh(cls, *, queryset: QuerySet[WirelessChassis]) -> ChassisRefreshResult:
        """Refresh a scoped selection and report successes without aborting siblings."""
        synced_count = 0
        failed_count = 0
        for chassis in queryset.select_related("manufacturer").order_by("pk"):
            try:
                refreshed = cls._refresh_chassis(chassis)
            except Exception:
                logger.exception("Failed to refresh chassis %s", chassis.pk)
                refreshed = False
            synced_count += int(refreshed)
            failed_count += int(not refreshed)

        return ChassisRefreshResult(
            synced_count=synced_count,
            failed_count=failed_count,
        )

    @classmethod
    def refresh_ids(
        cls,
        *,
        chassis_ids: list[int],
        using: str = DEFAULT_DB_ALIAS,
    ) -> ChassisRefreshResult:
        """Refresh only an explicit, serializable chassis selection."""
        from micboard.models.hardware.wireless_chassis import WirelessChassis

        selected_ids = sorted({chassis_id for chassis_id in chassis_ids if chassis_id > 0})
        queryset = WirelessChassis._default_manager.using(using).filter(pk__in=selected_ids)
        result = cls.refresh(queryset=queryset)
        missing_count = len(selected_ids) - queryset.count()
        return ChassisRefreshResult(
            synced_count=result.synced_count,
            failed_count=result.failed_count + missing_count,
        )
