"""Tenant-preserving refresh workflow for selected wireless chassis."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from itertools import islice
from typing import TYPE_CHECKING, Any

from django.contrib.auth import get_user_model
from django.db import DEFAULT_DB_ALIAS, transaction
from django.utils import timezone

from micboard.services.hardware.dtos import ChassisRefreshResult
from micboard.utils.exception_logging import sanitized_exception_info

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from micboard.models.hardware.wireless_chassis import WirelessChassis

logger = logging.getLogger(__name__)

MAX_CHASSIS_REFRESH_BATCH = 100


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
            except Exception as exc:
                logger.exception(
                    "Failed to refresh chassis %s",
                    chassis.pk,
                    exc_info=sanitized_exception_info(exc),
                )
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

    @classmethod
    def refresh_authorized_ids(
        cls,
        *,
        chassis_ids: Iterable[int],
        actor_id: int,
        using: str = DEFAULT_DB_ALIAS,
    ) -> ChassisRefreshResult:
        """Revalidate a bounded queued selection against the initiating operator."""
        from micboard.models.base_managers import TenantOptimizedQuerySet
        from micboard.models.hardware.wireless_chassis import WirelessChassis

        bounded_ids = list(islice(chassis_ids, MAX_CHASSIS_REFRESH_BATCH + 1))
        truncated = len(bounded_ids) > MAX_CHASSIS_REFRESH_BATCH
        selected_ids = sorted(
            {
                chassis_id
                for chassis_id in bounded_ids[:MAX_CHASSIS_REFRESH_BATCH]
                if isinstance(chassis_id, int)
                and not isinstance(chassis_id, bool)
                and chassis_id > 0
            }
        )

        user_model = get_user_model()
        try:
            actor = user_model._default_manager.using(using).get(pk=actor_id)
        except user_model.DoesNotExist:
            actor = None
        if (
            actor is None
            or not actor.is_active
            or not actor.is_staff
            or not actor.has_perm("micboard.change_wirelesschassis")
        ):
            return ChassisRefreshResult(
                synced_count=0,
                failed_count=len(selected_ids),
                denied=True,
                truncated=truncated,
            )

        visible: QuerySet[WirelessChassis] = TenantOptimizedQuerySet(
            WirelessChassis,
            using=using,
        ).for_user(user=actor)
        queryset = visible.filter(pk__in=selected_ids)
        visible_count = queryset.count()
        result = cls.refresh(queryset=queryset)
        return ChassisRefreshResult(
            synced_count=result.synced_count,
            failed_count=result.failed_count + len(selected_ids) - visible_count,
            truncated=truncated,
        )
