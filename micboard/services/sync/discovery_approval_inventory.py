"""Locked inventory snapshot for discovery approval planning."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Q

from micboard.discovery.limits import MAX_DISCOVERY_APPROVAL_INVENTORY_LOCKS
from micboard.models.discovery.queue import DiscoveryQueue
from micboard.models.hardware.charger import Charger
from micboard.models.hardware.wireless_chassis import WirelessChassis
from micboard.services.shared.base_dto import PydanticBaseDTO


class ApprovalIPOwners(PydanticBaseDTO):
    """Inventory rows locked for the IP addresses in one approval batch."""

    chassis_ids: dict[str, tuple[int, ...]]
    charger_ids: dict[str, tuple[int, ...]]


class LockedApprovalInventory(PydanticBaseDTO):
    """Stable, pre-locked inventory candidates for one approval batch."""

    chassis: tuple[WirelessChassis, ...]
    chargers: tuple[Charger, ...]
    owners: ApprovalIPOwners
    chassis_by_pk: dict[int, WirelessChassis]
    chargers_by_pk: dict[int, Charger]
    chassis_by_api_identity: dict[tuple[int, str], tuple[WirelessChassis, ...]]
    chassis_by_serial_identity: dict[tuple[int, str], tuple[WirelessChassis, ...]]
    chargers_by_serial_identity: dict[tuple[int | None, str], tuple[Charger, ...]]

    @staticmethod
    def _text(value: Any) -> str:
        """Normalize identity text used while building snapshot indexes."""
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _owner_ids_by_ip(rows: tuple[Any, ...]) -> dict[str, tuple[int, ...]]:
        """Preserve every locked owner ID instead of silently collapsing duplicates."""
        grouped_ids: dict[str, list[int]] = {}
        for row in rows:
            grouped_ids.setdefault(str(row.ip), []).append(int(row.pk))
        return {ip: tuple(owner_ids) for ip, owner_ids in grouped_ids.items()}

    @classmethod
    def _inventory_indexes(
        cls,
        chassis: tuple[WirelessChassis, ...],
        chargers: tuple[Charger, ...],
    ) -> dict[str, Any]:
        """Index locked rows once while preserving duplicate identity candidates."""
        chassis_by_api_identity: dict[tuple[int, str], list[WirelessChassis]] = {}
        chassis_by_serial_identity: dict[tuple[int, str], list[WirelessChassis]] = {}
        for chassis_row in chassis:
            api_device_id = cls._text(chassis_row.api_device_id)
            serial_number = cls._text(chassis_row.serial_number)
            if api_device_id:
                chassis_by_api_identity.setdefault(
                    (chassis_row.manufacturer_id, api_device_id), []
                ).append(chassis_row)
            if serial_number:
                chassis_by_serial_identity.setdefault(
                    (chassis_row.manufacturer_id, serial_number), []
                ).append(chassis_row)

        chargers_by_serial_identity: dict[tuple[int | None, str], list[Charger]] = {}
        for charger in chargers:
            serial_number = cls._text(charger.serial_number)
            if serial_number:
                chargers_by_serial_identity.setdefault(
                    (charger.manufacturer_id, serial_number), []
                ).append(charger)

        return {
            "chassis_by_pk": {int(row.pk): row for row in chassis},
            "chargers_by_pk": {int(row.pk): row for row in chargers},
            "chassis_by_api_identity": {
                identity: tuple(rows) for identity, rows in chassis_by_api_identity.items()
            },
            "chassis_by_serial_identity": {
                identity: tuple(rows) for identity, rows in chassis_by_serial_identity.items()
            },
            "chargers_by_serial_identity": {
                identity: tuple(rows) for identity, rows in chargers_by_serial_identity.items()
            },
        }

    @classmethod
    def lock(
        cls,
        items: list[DiscoveryQueue],
        *,
        using: str = "default",
    ) -> LockedApprovalInventory:
        """Lock every possible owner and target once in stable per-model PK order."""
        requested_ips = sorted({str(item.ip) for item in items})
        requested_ip_set = set(requested_ips)
        chassis_filter = Q(ip__in=requested_ips)
        charger_filter = Q(ip__in=requested_ips)

        for item in items:
            if item.device_type.lower() == "charger":
                if item.existing_charger_id is not None:
                    charger_filter |= Q(pk=item.existing_charger_id)
                serial_number = cls._text(item.serial_number)
                if serial_number:
                    charger_filter |= Q(
                        manufacturer_id=item.manufacturer_id,
                        serial_number=serial_number,
                    )
                continue

            identity_filter = cls._chassis_identity_filter(
                item=item,
                api_device_id=cls._text(item.api_device_id),
                serial_number=cls._text(item.serial_number),
            )
            if identity_filter is not None:
                chassis_filter |= identity_filter

        chassis = tuple(
            WirelessChassis.objects.using(using)
            .select_for_update()
            .filter(chassis_filter)
            .order_by("pk")[: MAX_DISCOVERY_APPROVAL_INVENTORY_LOCKS + 1]
        )
        if len(chassis) > MAX_DISCOVERY_APPROVAL_INVENTORY_LOCKS:
            raise ValidationError(
                "Discovery approval inventory lock scope exceeds hard limit of "
                f"{MAX_DISCOVERY_APPROVAL_INVENTORY_LOCKS} per hardware type."
            )
        chargers = tuple(
            Charger.objects.using(using)
            .select_for_update()
            .filter(charger_filter)
            .order_by("pk")[: MAX_DISCOVERY_APPROVAL_INVENTORY_LOCKS + 1]
        )
        if len(chargers) > MAX_DISCOVERY_APPROVAL_INVENTORY_LOCKS:
            raise ValidationError(
                "Discovery approval inventory lock scope exceeds hard limit of "
                f"{MAX_DISCOVERY_APPROVAL_INVENTORY_LOCKS} per hardware type."
            )
        owners = ApprovalIPOwners(
            chassis_ids=cls._owner_ids_by_ip(
                tuple(
                    chassis_row
                    for chassis_row in chassis
                    if str(chassis_row.ip) in requested_ip_set
                )
            ),
            charger_ids=cls._owner_ids_by_ip(
                tuple(charger for charger in chargers if str(charger.ip) in requested_ip_set)
            ),
        )
        return cls(
            chassis=chassis,
            chargers=chargers,
            owners=owners,
            **cls._inventory_indexes(chassis, chargers),
        )

    @staticmethod
    def _chassis_identity_filter(
        *,
        item: DiscoveryQueue,
        api_device_id: str,
        serial_number: str,
    ) -> Q | None:
        """Combine explicit and durable chassis identifiers for one locked lookup."""
        identity_filter: Q | None = None
        for identity in (
            Q(pk=item.existing_device_id) if item.existing_device_id is not None else None,
            (
                Q(manufacturer_id=item.manufacturer_id, api_device_id=api_device_id)
                if api_device_id
                else None
            ),
            (
                Q(manufacturer_id=item.manufacturer_id, serial_number=serial_number)
                if serial_number
                else None
            ),
        ):
            if identity is not None:
                identity_filter = (
                    identity if identity_filter is None else identity_filter | identity
                )
        return identity_filter
