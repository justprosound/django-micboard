"""Atomic approval workflow for staged discovery queue entries."""

from __future__ import annotations

from typing import Any, cast

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, QuerySet
from django.db.models.functions import Trim
from django.utils import timezone

from micboard.discovery.limits import MAX_DISCOVERY_APPROVAL_BATCH
from micboard.models.discovery.discovery_queue import DiscoveryQueue
from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.hardware.charger import Charger
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.hardware.dtos import WirelessChassisWrite
from micboard.services.hardware.ip_ownership_service import HardwareIPOwnershipService
from micboard.services.hardware.wireless_chassis_persistence_service import (
    WirelessChassisPersistenceService,
)
from micboard.services.shared.base_dto import PydanticBaseDTO
from micboard.services.sync.discovery_approval_plan import DiscoveryApprovalPlan
from micboard.services.sync.discovery_approval_resolution import (
    ChassisApprovalTarget,
    DiscoveryApprovalResolver,
)


class DiscoveryApprovalResult(PydanticBaseDTO):
    """Summary of one discovery approval transaction."""

    imported_count: int
    created_count: int
    updated_count: int


class DiscoveryApprovalPersistence(PydanticBaseDTO):
    """Persisted inventory targets and unique write counts."""

    chargers: dict[int, Charger]
    chassis: dict[int, WirelessChassis]
    created_count: int
    updated_count: int


class DiscoveryApprovalService:
    """Validate and atomically promote pending discovery queue entries."""

    @staticmethod
    def _preflight_target_permissions(
        queryset: QuerySet[DiscoveryQueue],
        *,
        reviewer: Any,
    ) -> None:
        """Reject missing target permissions before validation or row locks."""
        chassis = WirelessChassis.objects.using(queryset.db)
        selected_targets = cast(
            list[tuple[str, int | None, str, str, bool, bool]],
            list(
                queryset.filter(status="pending")
                .order_by("pk")
                .annotate(
                    approval_api_device_id=Trim("api_device_id"),
                    approval_serial_number=Trim("serial_number"),
                )
                .annotate(
                    approval_api_target_exists=Exists(
                        chassis.filter(
                            manufacturer_id=OuterRef("manufacturer_id"),
                            api_device_id=OuterRef("approval_api_device_id"),
                        )
                    ),
                    approval_serial_target_exists=Exists(
                        chassis.filter(
                            manufacturer_id=OuterRef("manufacturer_id"),
                            serial_number=OuterRef("approval_serial_number"),
                        )
                    ),
                )
                .values_list(
                    "device_type",
                    "existing_device_id",
                    "approval_api_device_id",
                    "approval_serial_number",
                    "approval_api_target_exists",
                    "approval_serial_target_exists",
                )[: MAX_DISCOVERY_APPROVAL_BATCH + 1]
            ),
        )
        required_permissions: set[str] = set()
        for (
            device_type,
            existing_device_id,
            api_device_id,
            serial_number,
            api_target_exists,
            serial_target_exists,
        ) in selected_targets:
            if str(device_type).lower() == "charger":
                required_permissions.add("micboard.change_charger")
                continue
            target_exists = bool(
                existing_device_id is not None
                or (api_device_id and api_target_exists)
                or (serial_number and serial_target_exists)
            )
            permission = (
                "micboard.change_wirelesschassis"
                if target_exists
                else "micboard.add_wirelesschassis"
            )
            required_permissions.add(permission)

        if required_permissions and not reviewer.has_perms(required_permissions):
            raise PermissionDenied

    @staticmethod
    def _lock_items(
        queryset: QuerySet[DiscoveryQueue],
        *,
        using: str,
    ) -> list[DiscoveryQueue]:
        """Lock every pending queue row sharing a requested IP in stable order."""
        requested_rows = list(
            queryset.select_related(None)
            .filter(status="pending")
            .order_by("pk")
            .values_list("pk", "ip")[: MAX_DISCOVERY_APPROVAL_BATCH + 1]
        )
        if len(requested_rows) > MAX_DISCOVERY_APPROVAL_BATCH:
            raise ValidationError(
                f"Discovery approval batch exceeds hard limit of {MAX_DISCOVERY_APPROVAL_BATCH}."
            )
        if not requested_rows:
            return []

        requested_ids = {pk for pk, _ip in requested_rows}
        requested_ips = sorted({str(ip) for _pk, ip in requested_rows})
        locked_rows = list(
            DiscoveryQueue.objects.using(using)
            .select_for_update()
            .filter(status="pending", ip__in=requested_ips)
            .order_by("pk")[: MAX_DISCOVERY_APPROVAL_BATCH + 1]
        )
        if len(locked_rows) > MAX_DISCOVERY_APPROVAL_BATCH:
            raise ValidationError(
                "Discovery approval conflict scope exceeds hard limit of "
                f"{MAX_DISCOVERY_APPROVAL_BATCH}."
            )
        selected_ids = [row.pk for row in locked_rows if row.pk in requested_ids]
        if not selected_ids:
            return []

        manufacturer_ids = sorted({row.manufacturer_id for row in locked_rows})
        list(
            Manufacturer.objects.using(using)
            .select_for_update()
            .filter(pk__in=manufacturer_ids)
            .order_by("pk")
        )
        return list(
            DiscoveryQueue.objects.using(using)
            .filter(pk__in=selected_ids, status="pending")
            .select_related("manufacturer")
            .order_by("pk")
        )

    @staticmethod
    def _adopt_wireless_chassis(
        entries: list[tuple[DiscoveryQueue, ChassisApprovalTarget]],
        *,
        using: str,
    ) -> tuple[WirelessChassis, bool]:
        """Apply an ordered logical-target group with one inventory save."""
        chassis = entries[0][1].chassis
        values: dict[str, Any] = {}
        for item, target in entries:
            values.update(DiscoveryApprovalResolver.chassis_values(item, target))
        write = WirelessChassisWrite(**values)

        if chassis is None:
            return (
                WirelessChassisPersistenceService.create(
                    write=write,
                    using=using,
                ),
                True,
            )

        return (
            WirelessChassisPersistenceService.update(
                chassis=chassis,
                write=write,
                using=using,
                save_all_fields=True,
            ),
            False,
        )

    @staticmethod
    def _adopt_charger(
        items: list[DiscoveryQueue],
        charger: Charger,
        *,
        using: str,
    ) -> Charger:
        """Apply an ordered charger-target group with one inventory save."""
        values: dict[str, Any] = {}
        for item in items:
            values.update(
                {
                    "manufacturer": item.manufacturer,
                    "ip": item.ip,
                    "status": "online",
                    "is_active": True,
                }
            )
            optional_values = {
                "name": DiscoveryApprovalResolver.text(item.name),
                "fqdn": DiscoveryApprovalResolver.text(item.fqdn),
                "model": DiscoveryApprovalResolver.text(item.model),
                "firmware_version": DiscoveryApprovalResolver.text(item.firmware_version),
            }
            values.update({key: value for key, value in optional_values.items() if value})

        for field_name, value in values.items():
            setattr(charger, field_name, value)
        charger.save(update_fields={*values, "updated_at"}, using=using)
        return charger

    @staticmethod
    def _chassis_group_key(
        item: DiscoveryQueue,
        target: ChassisApprovalTarget,
    ) -> tuple[str, int, str]:
        """Return one stable key for an existing chassis or new durable identity."""
        if target.chassis is None:
            return ("chassis_identity", item.manufacturer_id, target.api_device_id)
        if target.chassis.pk is None:  # pragma: no cover - locked model contract guard
            raise ValueError("A persisted chassis target is required.")
        return ("chassis", target.chassis.pk, "")

    def _persist_targets(
        self,
        items: list[DiscoveryQueue],
        plan: DiscoveryApprovalPlan,
        *,
        using: str,
    ) -> DiscoveryApprovalPersistence:
        """Coalesce queue rows by logical target and persist each target once."""
        charger_groups: dict[int, list[DiscoveryQueue]] = {}
        chassis_groups: dict[
            tuple[str, int, str],
            list[tuple[DiscoveryQueue, ChassisApprovalTarget]],
        ] = {}
        for item in items:
            if item.device_type.lower() == "charger":
                charger = plan.chargers[item.pk]
                if charger.pk is None:  # pragma: no cover - locked model contract guard
                    raise ValueError("A persisted charger target is required.")
                charger_groups.setdefault(charger.pk, []).append(item)
            else:
                target = plan.chassis[item.pk]
                key = self._chassis_group_key(item, target)
                chassis_groups.setdefault(key, []).append((item, target))

        approved_chargers: dict[int, Charger] = {}
        for grouped_items in charger_groups.values():
            first_item = grouped_items[0]
            charger = self._adopt_charger(
                grouped_items,
                plan.chargers[first_item.pk],
                using=using,
            )
            approved_chargers.update({item.pk: charger for item in grouped_items})

        approved_chassis: dict[int, WirelessChassis] = {}
        created_count = 0
        updated_chassis_count = 0
        for entries in chassis_groups.values():
            chassis, created = self._adopt_wireless_chassis(entries, using=using)
            created_count += int(created)
            updated_chassis_count += int(not created)
            approved_chassis.update({item.pk: chassis for item, _target in entries})

        return DiscoveryApprovalPersistence(
            chargers=approved_chargers,
            chassis=approved_chassis,
            created_count=created_count,
            updated_count=len(charger_groups) + updated_chassis_count,
        )

    @staticmethod
    def _mark_imported(
        *,
        items: list[DiscoveryQueue],
        persistence: DiscoveryApprovalPersistence,
        reviewer: Any,
        using: str,
    ) -> None:
        """Record inventory links and review metadata for every imported row."""
        reviewed_at = timezone.now()
        for item in items:
            if item.device_type.lower() == "charger":
                item.existing_charger = persistence.chargers[item.pk]
            else:
                item.existing_device = persistence.chassis[item.pk]
            item.status = "imported"
            item.reviewed_at = reviewed_at
            item.reviewed_by = reviewer
        DiscoveryQueue.objects.using(using).bulk_update(
            items,
            fields=(
                "existing_charger",
                "existing_device",
                "status",
                "reviewed_at",
                "reviewed_by",
            ),
        )

    def approve(
        self,
        *,
        queryset: QuerySet[DiscoveryQueue],
        reviewer: Any,
    ) -> DiscoveryApprovalResult:
        """Import pending entries once and record their reviewer atomically."""
        if not reviewer.has_perms({"micboard.change_discoveryqueue"}):
            raise PermissionDenied
        self._preflight_target_permissions(queryset, reviewer=reviewer)

        using = queryset.db
        with transaction.atomic(using=using):
            items = self._lock_items(queryset, using=using)
            HardwareIPOwnershipService.lock_addresses(
                (item.ip for item in items),
                using=using,
            )
            plan = DiscoveryApprovalPlan.build(items, using=using)

            if not reviewer.has_perms(plan.required_permissions):
                raise PermissionDenied

            persistence = self._persist_targets(items, plan, using=using)
            self._mark_imported(
                items=items,
                persistence=persistence,
                reviewer=reviewer,
                using=using,
            )

        return DiscoveryApprovalResult(
            imported_count=len(items),
            created_count=persistence.created_count,
            updated_count=persistence.updated_count,
        )
