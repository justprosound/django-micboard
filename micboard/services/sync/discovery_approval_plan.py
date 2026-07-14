"""Validated target plan for one locked discovery approval batch."""

from __future__ import annotations

from micboard.models.discovery.queue import DiscoveryQueue
from micboard.models.hardware.charger import Charger
from micboard.services.shared.base_dto import PydanticBaseDTO
from micboard.services.sync.discovery_approval_inventory import LockedApprovalInventory
from micboard.services.sync.discovery_approval_policy import DiscoveryApprovalBatchPolicy
from micboard.services.sync.discovery_approval_resolution import (
    ChassisApprovalTarget,
    DiscoveryApprovalResolver,
)


class DiscoveryApprovalPlan(PydanticBaseDTO):
    """Validated inventory targets and permissions for one approval batch."""

    chargers: dict[int, Charger]
    chassis: dict[int, ChassisApprovalTarget]
    required_permissions: frozenset[str]

    @classmethod
    def build(
        cls,
        items: list[DiscoveryQueue],
        *,
        using: str,
    ) -> DiscoveryApprovalPlan:
        """Lock inventory and resolve every selected row into one coherent plan."""
        inventory = LockedApprovalInventory.lock(items, using=using)
        batch_policy = DiscoveryApprovalBatchPolicy(owners=inventory.owners)
        charger_targets: dict[int, Charger] = {}
        chassis_targets: dict[int, ChassisApprovalTarget] = {}
        required_permissions = {"micboard.change_discoveryqueue"}

        for item in items:
            DiscoveryApprovalResolver.validate_role(item)
            if item.device_type.lower() == "charger":
                charger = DiscoveryApprovalResolver.resolve_charger(item, inventory=inventory)
                batch_policy.validate_charger(item=item, charger=charger)
                charger_targets[item.pk] = charger
                required_permissions.add("micboard.change_charger")
                continue

            target = DiscoveryApprovalResolver.resolve_chassis(item, inventory=inventory)
            batch_policy.validate_chassis(item=item, target=target)
            chassis_targets[item.pk] = target
            permission = (
                "micboard.add_wirelesschassis"
                if target.chassis is None
                else "micboard.change_wirelesschassis"
            )
            required_permissions.add(permission)

        return cls(
            chargers=charger_targets,
            chassis=chassis_targets,
            required_permissions=frozenset(required_permissions),
        )
