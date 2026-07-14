"""Atomic approval workflow for staged discovery queue entries."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from micboard.models.discovery.manufacturer import Manufacturer
from micboard.models.discovery.queue import DiscoveryQueue
from micboard.models.hardware.charger import Charger
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.hardware.dtos import WirelessChassisWrite
from micboard.services.hardware.ip_ownership_service import HardwareIPOwnershipService
from micboard.services.hardware.wireless_chassis_persistence_service import (
    WirelessChassisPersistenceService,
)
from micboard.services.shared.base_dto import PydanticBaseDTO
from micboard.services.sync.discovery_approval_policy import DiscoveryApprovalBatchPolicy
from micboard.services.sync.discovery_approval_resolution import (
    ChassisApprovalTarget,
    DiscoveryApprovalResolver,
    LockedApprovalInventory,
)


class DiscoveryApprovalResult(PydanticBaseDTO):
    """Summary of one discovery approval transaction."""

    imported_count: int
    created_count: int
    updated_count: int


class DiscoveryApprovalTargets(PydanticBaseDTO):
    """Validated inventory targets keyed by queue row."""

    chargers: dict[int, Charger]
    chassis: dict[int, ChassisApprovalTarget]


class DiscoveryApprovalPersistence(PydanticBaseDTO):
    """Persisted inventory targets and unique write counts."""

    chargers: dict[int, Charger]
    chassis: dict[int, WirelessChassis]
    created_count: int
    updated_count: int


class DiscoveryApprovalService:
    """Validate and atomically promote pending discovery queue entries."""

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
            .values_list("pk", "ip")
        )
        if not requested_rows:
            return []

        requested_ids = {pk for pk, _ip in requested_rows}
        requested_ips = sorted({str(ip) for _pk, ip in requested_rows})
        locked_rows = list(
            DiscoveryQueue.objects.using(using)
            .select_for_update()
            .filter(status="pending", ip__in=requested_ips)
            .order_by("pk")
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
    def _required_permissions(
        items: list[DiscoveryQueue],
        chassis_targets: dict[int, ChassisApprovalTarget],
    ) -> set[str]:
        """Return the least-privilege target permissions needed by this batch."""
        permissions = {"micboard.change_discoveryqueue"}
        for item in items:
            if item.device_type.lower() == "charger":
                permissions.add("micboard.change_charger")
            elif chassis_targets[item.pk].chassis is None:
                permissions.add("micboard.add_wirelesschassis")
            else:
                permissions.add("micboard.change_wirelesschassis")
        return permissions

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

    @staticmethod
    def _resolve_targets(
        items: list[DiscoveryQueue],
        batch_policy: DiscoveryApprovalBatchPolicy,
        inventory: LockedApprovalInventory,
    ) -> DiscoveryApprovalTargets:
        """Resolve and validate one locked inventory target per queue row."""
        charger_targets: dict[int, Charger] = {}
        chassis_targets: dict[int, ChassisApprovalTarget] = {}
        for item in items:
            DiscoveryApprovalResolver.validate_role(item)
            if item.device_type.lower() == "charger":
                charger = DiscoveryApprovalResolver.resolve_charger(item, inventory=inventory)
                batch_policy.validate_charger(item=item, charger=charger)
                charger_targets[item.pk] = charger
            else:
                target = DiscoveryApprovalResolver.resolve_chassis(item, inventory=inventory)
                batch_policy.validate_chassis(item=item, target=target)
                chassis_targets[item.pk] = target
        return DiscoveryApprovalTargets(chargers=charger_targets, chassis=chassis_targets)

    def _persist_targets(
        self,
        items: list[DiscoveryQueue],
        targets: DiscoveryApprovalTargets,
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
                charger = targets.chargers[item.pk]
                if charger.pk is None:  # pragma: no cover - locked model contract guard
                    raise ValueError("A persisted charger target is required.")
                charger_groups.setdefault(charger.pk, []).append(item)
            else:
                target = targets.chassis[item.pk]
                key = self._chassis_group_key(item, target)
                chassis_groups.setdefault(key, []).append((item, target))

        approved_chargers: dict[int, Charger] = {}
        for grouped_items in charger_groups.values():
            first_item = grouped_items[0]
            charger = self._adopt_charger(
                grouped_items,
                targets.chargers[first_item.pk],
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
        using = queryset.db
        with transaction.atomic(using=using):
            items = self._lock_items(queryset, using=using)
            HardwareIPOwnershipService.lock_addresses(
                (item.ip for item in items),
                using=using,
            )
            inventory = DiscoveryApprovalResolver.lock_inventory(items, using=using)
            batch_policy = DiscoveryApprovalBatchPolicy(owners=inventory.owners)
            targets = self._resolve_targets(items, batch_policy, inventory)

            if not reviewer.has_perms(self._required_permissions(items, targets.chassis)):
                raise PermissionDenied

            persistence = self._persist_targets(items, targets, using=using)
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
